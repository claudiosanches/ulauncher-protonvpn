"""
ProtonVPN core manager.

Wraps the `protonvpn` CLI to provide connect, disconnect, status,
country listing, and city listing functionality.
"""

import json
import pathlib
import re
import shutil
import subprocess
import threading
import time
from typing import Optional

# TODO: Add support for Secure Core, P2P and Tor connection types via a
#       preference setting that appends --securecore, --p2p or --tor to
#       all connect calls.

# TODO: Add optional external IP check preference (pvpn_ip_check).
#       When enabled, fetch the current public IP from a third-party
#       endpoint and display it in the status view.  The README must
#       disclose which endpoint is used.


class ProtonVPN:
    """Interact with the protonvpn CLI."""

    BINARY = "protonvpn"
    STATUS_TTL = 10  # seconds before re-querying protonvpn status
    CACHE_FILE = pathlib.Path(__file__).parent.parent / ".data" / "cache.json"

    def __init__(self) -> None:
        # In-memory caches — populated from disk on first access.
        self._countries: list[dict] = []
        self._cities: dict[str, list[dict]] = {}
        # IP cached from the last successful connect call.
        self._last_ip: Optional[str] = None
        # Status cache — served immediately; refreshed in background.
        self._status_cache: Optional[dict] = None
        self._status_cache_empty: bool = True
        self._status_ts: float = 0.0
        self._status_refreshing: bool = False
        # Load persisted cache from disk.
        self._load_cache()

    # ------------------------------------------------------------------
    # Installation check
    # ------------------------------------------------------------------

    def is_installed(self) -> bool:
        """Return True if the protonvpn binary is available on PATH."""
        return shutil.which(self.BINARY) is not None

    # ------------------------------------------------------------------
    # Country / city discovery
    # ------------------------------------------------------------------

    def has_cache(self) -> bool:
        """Return True when the in-memory country list has entries."""
        return len(self._countries) > 0

    def get_countries(self) -> list[dict]:
        """
        Return the cached list of available countries.

        Returns whatever was last saved by refresh_cache().  Returns an
        empty list when the cache file does not exist yet.

        Each entry is a dict with keys:
            name  – human-readable country name (e.g. "United States")
            code  – two-letter ISO code        (e.g. "US")
        """
        return self._countries

    def get_cities(self, country_code: str) -> list[dict]:
        """
        Return the list of cities for *country_code* from cache.

        Returns the cached list immediately (never blocks).  Returns an
        empty list when the country has not been fetched yet — callers
        should use fetch_cities() in a background thread to populate the
        cache, then call this method again.

        Each entry is a dict with keys:
            name      – city name     (e.g. "New York")
            features  – feature tags  (e.g. "P2P, Tor") or ""
        """
        return self._cities.get(country_code.upper(), [])

    def has_cities(self, country_code: str) -> bool:
        """Return True if cities for *country_code* are already cached."""
        return country_code.upper() in self._cities

    def fetch_cities(self, country_code: str) -> list[dict]:
        """
        Fetch cities for *country_code* from the CLI and persist to cache.

        This call is blocking (CLI subprocess).  Run it in a background
        thread and use get_cities() to read the result.  Returns the
        fetched list, or [] on failure.
        """
        key = country_code.upper()
        result = self._run(["cities", "list", key])
        if result is None:
            return []

        cities = []
        in_table = False
        for line in result.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("City"):
                in_table = True
                continue
            if stripped.startswith("---"):
                continue
            if stripped.lower().startswith("cities in"):
                continue
            if in_table:
                parts = re.split(r"\s{2,}", stripped, maxsplit=1)
                name = parts[0].strip()
                features = parts[1].strip() if len(parts) > 1 else ""
                if name:
                    cities.append({"name": name, "features": features})

        self._cities[key] = cities
        self._save_cache()
        return cities

    def refresh_cache(self) -> bool:
        """
        Fetch the country list from the CLI and persist it to disk.

        Only countries are saved — cities are fetched on demand per session.
        Returns True when at least one country was fetched and saved.
        """
        result = self._run(["countries", "list"])
        if result is None:
            return False

        countries = []
        for line in result.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("Country")
                or stripped.startswith("---")
            ):
                continue
            parts = stripped.rsplit(None, 1)
            if len(parts) == 2 and re.fullmatch(r"[A-Z]{2}", parts[1]):
                countries.append({"name": parts[0].strip(), "code": parts[1]})

        if not countries:
            return False

        self._countries = countries
        self._cities = {}  # clear stale city cache — will re-populate on demand
        self._save_cache()
        return True

    def clear_cache(self) -> None:
        """Delete the cache file and clear in-memory data."""
        self._countries = []
        self._cities = {}
        self._status_ts = 0.0
        try:
            self.CACHE_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Cache persistence
    # ------------------------------------------------------------------

    def _load_cache(self) -> None:
        """
        Load countries, cities, and last known status from the cache file.

        Invalid or missing cache files are treated as empty cache state.  The
        cache is only an optimization, so read failures should never prevent
        the extension from opening.
        """
        try:
            data = json.loads(self.CACHE_FILE.read_text())
            self._countries = data.get("countries", [])
            self._cities = data.get("cities", {})
            status = data.get("status")
            if status and status.get("server"):
                self._status_cache = status
                self._status_cache_empty = False
                # Treat persisted status as immediately valid so the first query
                # renders it right away.  Leave _status_ts = 0.0 so the TTL
                # check fires and the background thread (already started by
                # main.py with _status_refreshing = True) will refresh it.
        except (OSError, json.JSONDecodeError):
            self._countries = []
            self._cities = {}
            self._status_cache = None
            self._status_cache_empty = True

    def _save_cache(self) -> None:
        """
        Persist cache data to disk.

        Cache writes are best effort: the extension should continue to work
        even when the cache directory cannot be created or written.
        """
        try:
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.CACHE_FILE.write_text(
                json.dumps(
                    {
                        "countries": self._countries,
                        "cities": self._cities,
                        "status": self._status_cache,
                    }
                )
            )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(
        self,
        country_code: Optional[str] = None,
        city: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Connect to ProtonVPN.

        Parameters
        ----------
        country_code:
            Two-letter ISO country code.  When omitted the CLI will
            choose the fastest available server globally.
        city:
            City name.  Only used when *country_code* is also provided.

        Returns
        -------
        (success, ip)
            *success* is True when the CLI exits with code 0.
            *ip* is the new public IP parsed from the CLI output, or
            None when it cannot be determined.
        """
        cmd = ["connect"]
        if country_code:
            cmd += ["--country", country_code.upper()]
        if city:
            cmd += ["--city", city]

        output = self._run(cmd)
        if output is None:
            return False, None

        # Parse: "Your new IP address is X.X.X.X."
        match = re.search(r"Your new IP address is ([\d.]+?)\.?\s", output)
        ip = match.group(1) if match else None
        if ip:
            self._last_ip = ip

        success = "Connected to" in output
        if success:
            # Parse server name from "Connected to <server>."
            server_match = re.search(r"Connected to (.+?)\.", output)
            self._status_cache = {
                "server": server_match.group(1) if server_match else None,
                "load": None,
                "protocol": None,
                "ip": ip,
            }
            self._status_cache_empty = False
        else:
            self._status_cache = None
            self._status_cache_empty = True
        self._status_ts = 0.0  # still stale so background refresh fires on next query
        self._save_cache()
        return success, ip

    def disconnect(self) -> bool:
        """
        Disconnect from ProtonVPN.

        Returns True when the CLI reports a successful disconnection.
        """
        output = self._run(["disconnect"])
        if output is None:
            return False
        self._status_ts = 0.0  # force background refresh on next query
        self._status_cache = None  # don't serve stale connected state
        self._status_cache_empty = True
        self._save_cache()
        return "Disconnected" in output

    def get_status(self) -> Optional[dict]:
        """
        Return the current connection status.

        Always returns the cached value immediately (never blocks).  When the
        cache is stale (older than STATUS_TTL), a background thread is kicked
        off to refresh it — the updated value will appear on the next query.
        Connect/disconnect calls invalidate the cache so the refresh fires on
        the very next query.

        Returns
        -------
        None
            When not connected (or not yet known).
        dict
            When connected, with keys:
                server    – e.g. "BR#116 in São Paulo, Brazil"
                load      – e.g. "29%"
                protocol  – e.g. "wireguard"
                ip        – cached IP from last connect, or None
        """
        now = time.monotonic()
        if now - self._status_ts >= self.STATUS_TTL and not self._status_refreshing:
            self._status_refreshing = True
            threading.Thread(target=self._refresh_status, daemon=True).start()

        return None if self._status_cache_empty else self._status_cache

    def _refresh_status(self) -> None:
        """Background worker: fetch status from CLI and update the cache."""
        try:
            output = self._run(["status"])
            self._status_ts = time.monotonic()

            if output is None or "Disconnected" in output:
                self._last_ip = None
                self._status_cache = None
                self._status_cache_empty = True
                self._save_cache()
                return

            status: dict = {
                "server": None,
                "load": None,
                "protocol": None,
                "ip": self._last_ip,
            }
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("Server:"):
                    status["server"] = line.removeprefix("Server:").strip()
                elif line.startswith("Load:"):
                    status["load"] = line.removeprefix("Load:").strip()
                elif line.startswith("Protocol:"):
                    status["protocol"] = line.removeprefix("Protocol:").strip()

            if status["server"] is None:
                self._status_cache = None
                self._status_cache_empty = True
            else:
                self._status_cache = status
                self._status_cache_empty = False
            self._save_cache()
        finally:
            self._status_refreshing = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self, args: list[str]) -> Optional[str]:
        """
        Run ``protonvpn <args>`` and return stdout as a string on success,
        or None on non-zero exit code or execution error.

        stderr is intentionally ignored: CLI error messages should not flow
        into parsers as if they were valid output.
        """
        try:
            result = subprocess.run(
                [self.BINARY] + args,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return None
            return result.stdout or ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
