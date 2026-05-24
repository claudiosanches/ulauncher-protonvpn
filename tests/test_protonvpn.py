"""Tests for src/protonvpn.py"""

import json
import time
from unittest.mock import MagicMock, patch

from src.protonvpn import ProtonVPN


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

COUNTRIES_OUTPUT = """\
Server list is outdated, updating... This may take a moment.
Country                           Code
--------------------------------  ------
Brazil                            BR
Germany                           DE
United States                     US
Bosnia and Herzegovina            BA
"""

CITIES_US_OUTPUT = """\
Cities in United States:
City            Features
--------------  ----------
Ashburn         P2P
Atlanta         P2P, Tor
New York        P2P
"""

STATUS_CONNECTED = """\
Status: Connected
Server: BR#116 in São Paulo, Brazil
Load: 29%
Protocol: wireguard
"""

STATUS_DISCONNECTED = "Status: Disconnected\n"

CONNECT_OUTPUT = """\
Connected to BR#116 in São Paulo, Brazil.\x20
Your new IP address is 146.70.98.133.
"""

DISCONNECT_OUTPUT = "Disconnected.\n"


def _make_result(stdout="", returncode=0):
    r = MagicMock()
    r.stdout = stdout
    r.stderr = ""
    r.returncode = returncode
    return r


def _pvpn_no_cache():
    """Return a ProtonVPN instance with no disk cache."""
    pvpn = ProtonVPN()
    pvpn._countries = []
    pvpn._cities = {}
    return pvpn


# ---------------------------------------------------------------------------
# is_installed
# ---------------------------------------------------------------------------


class TestIsInstalled:
    def test_returns_true_when_binary_found(self):
        with patch("shutil.which", return_value="/usr/bin/protonvpn"):
            assert ProtonVPN().is_installed() is True

    def test_returns_false_when_binary_missing(self):
        with patch("shutil.which", return_value=None):
            assert ProtonVPN().is_installed() is False


# ---------------------------------------------------------------------------
# has_cache / _load_cache / _save_cache
# ---------------------------------------------------------------------------


class TestCachePersistence:
    def test_has_cache_false_when_no_countries_loaded(self):
        pvpn = ProtonVPN()
        pvpn._countries = []
        assert pvpn.has_cache() is False

    def test_has_cache_true_when_countries_loaded(self):
        pvpn = ProtonVPN()
        pvpn._countries = [{"name": "Brazil", "code": "BR"}]
        assert pvpn.has_cache() is True

    def test_has_cache_false_after_corrupt_file(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text("not json")
        pvpn = ProtonVPN()
        pvpn.CACHE_FILE = cache
        pvpn._load_cache()
        assert pvpn.has_cache() is False

    def test_load_cache_populates_countries_and_cities(self, tmp_path):
        data = {
            "countries": [{"name": "Brazil", "code": "BR"}],
            "cities": {"BR": [{"name": "São Paulo", "features": ""}]},
        }
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps(data))
        pvpn = ProtonVPN()
        pvpn.CACHE_FILE = cache
        pvpn._load_cache()
        assert pvpn._countries == data["countries"]

    def test_load_cache_handles_missing_file(self, tmp_path):
        pvpn = ProtonVPN()
        pvpn.CACHE_FILE = tmp_path / "missing.json"
        pvpn._load_cache()
        assert pvpn._countries == []

    def test_load_cache_handles_corrupt_file(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text("not json")
        pvpn = ProtonVPN()
        pvpn.CACHE_FILE = cache
        pvpn._load_cache()
        assert pvpn._countries == []

    def test_load_cache_clears_state_after_corrupt_file(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text("not json")
        pvpn = ProtonVPN()
        pvpn.CACHE_FILE = cache
        pvpn._countries = [{"name": "Brazil", "code": "BR"}]
        pvpn._cities = {"BR": [{"name": "São Paulo", "features": ""}]}
        pvpn._status_cache = {
            "server": "BR#1",
            "load": "10%",
            "protocol": "wireguard",
            "ip": None,
        }
        pvpn._status_cache_empty = False
        pvpn._load_cache()
        assert pvpn._countries == []
        assert pvpn._cities == {}
        assert pvpn._status_cache is None
        assert pvpn._status_cache_empty is True

    def test_save_cache_writes_json(self, tmp_path):
        pvpn = ProtonVPN()
        pvpn.CACHE_FILE = tmp_path / "cache.json"
        pvpn._countries = [{"name": "Germany", "code": "DE"}]
        pvpn._save_cache()
        data = json.loads(pvpn.CACHE_FILE.read_text())
        assert data["countries"] == [{"name": "Germany", "code": "DE"}]


# ---------------------------------------------------------------------------
# get_countries / get_cities
# ---------------------------------------------------------------------------


class TestGetCountries:
    def test_returns_in_memory_countries(self):
        pvpn = ProtonVPN()
        pvpn._countries = [{"name": "Brazil", "code": "BR"}]
        assert pvpn.get_countries() == [{"name": "Brazil", "code": "BR"}]

    def test_returns_empty_when_no_cache(self):
        pvpn = _pvpn_no_cache()
        assert pvpn.get_countries() == []


class TestGetCities:
    def test_returns_cities_from_memory_if_cached(self):
        pvpn = ProtonVPN()
        pvpn._cities = {"US": [{"name": "New York", "features": "P2P"}]}
        assert pvpn.get_cities("US") == [{"name": "New York", "features": "P2P"}]

    def test_uppercases_country_code(self):
        pvpn = ProtonVPN()
        pvpn._cities = {"US": [{"name": "New York", "features": "P2P"}]}
        assert pvpn.get_cities("us") == [{"name": "New York", "features": "P2P"}]

    def test_fetches_from_cli_when_not_cached(self):
        pvpn = _pvpn_no_cache()
        with patch("subprocess.run", return_value=_make_result(CITIES_US_OUTPUT)):
            cities = pvpn.fetch_cities("US")
        names = [c["name"] for c in cities]
        assert "New York" in names
        assert "Atlanta" in names

    def test_caches_result_in_memory(self):
        pvpn = _pvpn_no_cache()
        with patch(
            "subprocess.run",
            return_value=_make_result(CITIES_US_OUTPUT),
        ) as mock_run:
            pvpn.fetch_cities("US")
            pvpn.get_cities("US")  # second call — cache-only, no CLI
        assert mock_run.call_count == 1

    def test_returns_empty_on_cli_failure(self):
        pvpn = _pvpn_no_cache()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert pvpn.fetch_cities("XX") == []


# ---------------------------------------------------------------------------
# refresh_cache
# ---------------------------------------------------------------------------


class TestRefreshCache:
    def test_parses_and_saves_countries(self, tmp_path):
        pvpn = _pvpn_no_cache()
        pvpn.CACHE_FILE = tmp_path / "cache.json"
        with patch("subprocess.run", return_value=_make_result(COUNTRIES_OUTPUT)):
            result = pvpn.refresh_cache()
        assert result is True
        codes = [c["code"] for c in pvpn._countries]
        assert "BR" in codes
        assert "US" in codes

    def test_persists_to_disk(self, tmp_path):
        pvpn = _pvpn_no_cache()
        pvpn.CACHE_FILE = tmp_path / "cache.json"
        with patch("subprocess.run", return_value=_make_result(COUNTRIES_OUTPUT)):
            pvpn.refresh_cache()
        assert pvpn.CACHE_FILE.exists()
        data = json.loads(pvpn.CACHE_FILE.read_text())
        assert len(data["countries"]) > 0

    def test_returns_false_on_cli_failure(self, tmp_path):
        pvpn = _pvpn_no_cache()
        pvpn.CACHE_FILE = tmp_path / "cache.json"
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = pvpn.refresh_cache()
        assert result is False

    def test_skips_header_and_separator(self, tmp_path):
        pvpn = _pvpn_no_cache()
        pvpn.CACHE_FILE = tmp_path / "cache.json"
        with patch("subprocess.run", return_value=_make_result(COUNTRIES_OUTPUT)):
            pvpn.refresh_cache()
        codes = [c["code"] for c in pvpn._countries]
        assert "Co" not in codes

    def test_does_not_call_cities(self, tmp_path):
        pvpn = _pvpn_no_cache()
        pvpn.CACHE_FILE = tmp_path / "cache.json"
        with patch(
            "subprocess.run",
            return_value=_make_result(COUNTRIES_OUTPUT),
        ) as mock_run:
            pvpn.refresh_cache()
        # Only one subprocess call — countries list only
        assert mock_run.call_count == 1


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------


class TestClearCache:
    def test_clears_in_memory_data(self):
        pvpn = ProtonVPN()
        pvpn._countries = [{"name": "Brazil", "code": "BR"}]
        pvpn._cities = {"US": [{"name": "New York", "features": "P2P"}]}
        pvpn.clear_cache()
        assert pvpn._countries == []
        assert pvpn._cities == {}

    def test_deletes_cache_file(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text('{"countries":[],"cities":{}}')
        pvpn = ProtonVPN()
        pvpn.CACHE_FILE = cache
        pvpn.clear_cache()
        assert not cache.exists()


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


class TestConnect:
    def test_connect_fastest(self):
        pvpn = ProtonVPN()
        with patch(
            "subprocess.run",
            return_value=_make_result(CONNECT_OUTPUT),
        ) as mock_run:
            success, ip = pvpn.connect()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "connect" in args
        assert "--country" not in args
        assert success is True
        assert ip == "146.70.98.133"

    def test_connect_by_country(self):
        pvpn = ProtonVPN()
        with patch(
            "subprocess.run",
            return_value=_make_result(CONNECT_OUTPUT),
        ) as mock_run:
            success, ip = pvpn.connect(country_code="BR")

        args = mock_run.call_args[0][0]
        assert "--country" in args
        assert "BR" in args
        assert success is True

    def test_connect_by_country_and_city(self):
        pvpn = ProtonVPN()
        with patch(
            "subprocess.run",
            return_value=_make_result(CONNECT_OUTPUT),
        ) as mock_run:
            pvpn.connect(country_code="US", city="New York")

        args = mock_run.call_args[0][0]
        assert "--country" in args
        assert "US" in args
        assert "--city" in args
        assert "New York" in args

    def test_caches_ip_for_status(self):
        pvpn = ProtonVPN()
        with patch("subprocess.run", return_value=_make_result(CONNECT_OUTPUT)):
            pvpn.connect()

        assert pvpn._last_ip == "146.70.98.133"

    def test_returns_false_on_failure(self):
        pvpn = ProtonVPN()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            success, ip = pvpn.connect()

        assert success is False
        assert ip is None

    def test_updates_status_cache_on_connect(self):
        pvpn = ProtonVPN()
        pvpn._status_ts = time.monotonic()
        pvpn._status_cache = {
            "server": "BR#1",
            "load": "10%",
            "protocol": "wireguard",
            "ip": None,
        }
        pvpn._status_cache_empty = False
        with patch("subprocess.run", return_value=_make_result(CONNECT_OUTPUT)):
            pvpn.connect()
        assert pvpn._status_ts == 0.0
        assert pvpn._status_cache_empty is False
        assert pvpn._status_cache["server"] == "BR#116 in São Paulo, Brazil"
        assert pvpn._status_cache["ip"] == "146.70.98.133"


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    def test_returns_true_on_success(self):
        pvpn = ProtonVPN()
        with patch("subprocess.run", return_value=_make_result(DISCONNECT_OUTPUT)):
            assert pvpn.disconnect() is True

    def test_returns_false_on_failure(self):
        pvpn = ProtonVPN()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert pvpn.disconnect() is False

    def test_invalidates_status_cache(self):
        pvpn = ProtonVPN()
        pvpn._status_ts = time.monotonic()
        pvpn._status_cache = {
            "server": "BR#1",
            "load": "10%",
            "protocol": "wireguard",
            "ip": None,
        }
        pvpn._status_cache_empty = False
        with patch("subprocess.run", return_value=_make_result(DISCONNECT_OUTPUT)):
            pvpn.disconnect()
        assert pvpn._status_ts == 0.0
        assert pvpn._status_cache is None
        assert pvpn._status_cache_empty is True


# ---------------------------------------------------------------------------
# get_status (returns cached value immediately)
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_cached_value_without_calling_cli(self):
        pvpn = ProtonVPN()
        pvpn._status_cache = {
            "server": "BR#1",
            "load": "10%",
            "protocol": "wireguard",
            "ip": None,
        }
        pvpn._status_cache_empty = False
        pvpn._status_ts = time.monotonic()  # just refreshed — cache is fresh
        with patch("subprocess.run") as mock_run:
            status = pvpn.get_status()
        mock_run.assert_not_called()
        assert status is not None
        assert status["server"] == "BR#1"

    def test_returns_none_when_cache_empty(self):
        pvpn = ProtonVPN()
        pvpn._status_cache_empty = True
        pvpn._status_ts = time.monotonic()  # fresh, so no background refresh
        assert pvpn.get_status() is None

    def test_triggers_background_refresh_when_stale(self):
        pvpn = ProtonVPN()
        pvpn._status_ts = 0.0
        pvpn._status_refreshing = False
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            pvpn.get_status()
        mock_thread.assert_called_once()

    def test_does_not_spawn_duplicate_refresh(self):
        pvpn = ProtonVPN()
        pvpn._status_ts = 0.0
        pvpn._status_refreshing = True
        with patch("threading.Thread") as mock_thread:
            pvpn.get_status()
        mock_thread.assert_not_called()


# ---------------------------------------------------------------------------
# _refresh_status
# ---------------------------------------------------------------------------


class TestRefreshStatus:
    def test_populates_cache_when_connected(self):
        pvpn = ProtonVPN()
        pvpn._status_refreshing = True
        with patch("subprocess.run", return_value=_make_result(STATUS_CONNECTED)):
            pvpn._refresh_status()
        assert pvpn._status_cache_empty is False
        assert pvpn._status_cache is not None
        assert pvpn._status_cache["server"] == "BR#116 in São Paulo, Brazil"
        assert pvpn._status_refreshing is False

    def test_clears_cache_when_disconnected(self):
        pvpn = ProtonVPN()
        pvpn._last_ip = "1.2.3.4"
        pvpn._status_refreshing = True
        with patch("subprocess.run", return_value=_make_result(STATUS_DISCONNECTED)):
            pvpn._refresh_status()
        assert pvpn._status_cache_empty is True
        assert pvpn._last_ip is None
        assert pvpn._status_refreshing is False

    def test_clears_refreshing_flag_on_failure(self):
        pvpn = ProtonVPN()
        pvpn._status_refreshing = True
        with patch("subprocess.run", side_effect=FileNotFoundError):
            pvpn._refresh_status()
        assert pvpn._status_refreshing is False
