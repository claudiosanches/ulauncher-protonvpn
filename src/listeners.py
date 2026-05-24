"""
Ulauncher event listeners for the ProtonVPN extension.

Flow
----
Home screen (pvpn):
    1. Status (if connected) or "Connect" item
    2. Disconnect (if connected)
    3. Fetch / refresh server list

Connect screen — triggered by entering "Connect":
    1. Connect to fastest server (globally)
    2. <Country list, filtered by whatever the user types after the keyword>
       → selecting a country drills into the city screen

City screen — triggered by selecting a country:
    1. Fastest in <country>
    2. <City list>
       → selecting a city connects immediately

Navigation state is passed entirely through ExtensionCustomAction data.
The query bar is never polluted with internal prefixes.
"""

import re
import threading
from collections.abc import Callable

from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.HideWindowAction import HideWindowAction
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem

from src.utils import Utils


# ---------------------------------------------------------------------------
# Action constants
# ---------------------------------------------------------------------------
ACT_SHOW_CONNECT = "SHOW_CONNECT"
ACT_SHOW_CITIES = "SHOW_CITIES"
ACT_CONNECT_FASTEST = "CONNECT_FASTEST"
ACT_CONNECT_COUNTRY = "CONNECT_COUNTRY"
ACT_CONNECT_CITY = "CONNECT_CITY"
ACT_DISCONNECT = "DISCONNECT"
ACT_REFRESH = "REFRESH"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(name: str, description: str, icon: str, action) -> ExtensionResultItem:
    """Create a Ulauncher result item with the extension's common shape."""
    return ExtensionResultItem(
        icon=icon,
        name=name,
        description=description,
        on_enter=action,
    )


def _action(data: dict) -> ExtensionCustomAction:
    """Create an action that closes Ulauncher after execution."""
    return ExtensionCustomAction(data, keep_app_open=False)


def _action_keep(data: dict) -> ExtensionCustomAction:
    """Create an action that keeps Ulauncher open for the next screen."""
    return ExtensionCustomAction(data, keep_app_open=True)


def _run_in_background(target: Callable[[], None]) -> None:
    """Run *target* in a daemon thread without blocking the UI."""
    threading.Thread(target=target, daemon=True).start()


# ---------------------------------------------------------------------------
# KeywordQueryEventListener
# ---------------------------------------------------------------------------


class KeywordQueryEventListener(EventListener):
    """Render the home and selection screens for keyword queries."""

    def on_event(self, event, extension):
        """Route the current keyword query to the appropriate result list."""
        pvpn = extension.pvpn
        max_entries = extension.max_entries

        query = (event.get_argument() or "").strip()

        if query:
            # Any text typed after the keyword filters the country list.
            return RenderResultListAction(
                self._connect_screen(pvpn, query, max_entries)
            )

        return RenderResultListAction(self._home_screen(pvpn))

    # Screen builders

    def _home_screen(self, pvpn):
        """Build the top-level status, connect, disconnect, and refresh items."""
        icon = Utils.get_path("images/icon.svg")
        items = []
        status = pvpn.get_status()

        if status:
            server = status.get("server", "Unknown server")
            load = status.get("load", "?")
            protocol = status.get("protocol", "?")
            ip = status.get("ip")
            m = re.match(r"([A-Z]{2})#", server or "")
            flag = Utils.flag_path(m.group(1) if m else "")
            desc_parts = [f"Load: {load}", f"Protocol: {protocol}"]
            if ip:
                desc_parts.append(f"IP: {ip}")
            items.append(
                _item(
                    f"Connected: {server}",
                    " · ".join(desc_parts),
                    flag,
                    HideWindowAction(),
                )
            )
            items.append(
                _item(
                    "Disconnect",
                    "Disconnect from the current ProtonVPN server",
                    icon,
                    _action({"action": ACT_DISCONNECT}),
                )
            )
        else:
            items.append(
                _item(
                    "Connect to fastest server",
                    "Let ProtonVPN pick the fastest available server globally",
                    icon,
                    _action({"action": ACT_CONNECT_FASTEST}),
                )
            )
            items.append(
                _item(
                    "Connect to a country",
                    "Type the country name or code to filter the list",
                    icon,
                    _action_keep({"action": ACT_SHOW_CONNECT}),
                )
            )

        items.append(
            _item(
                "Refresh server list",
                "Download the country list from ProtonVPN"
                if not pvpn.has_cache()
                else "Re-download the country list from ProtonVPN",
                icon,
                _action({"action": ACT_REFRESH}),
            )
        )

        return items

    def _connect_screen(self, pvpn, country_filter, max_entries):
        """Build the country picker filtered by name or country code."""
        icon = Utils.get_path("images/icon.svg")
        items = []

        countries = pvpn.get_countries()
        q = country_filter.lower()
        matches = [
            c for c in countries if q in c["name"].lower() or q in c["code"].lower()
        ]
        matches = matches[:max_entries]

        if not matches:
            items.append(
                _item(
                    "No countries found",
                    f'No results matching "{country_filter}"',
                    icon,
                    HideWindowAction(),
                )
            )
        else:
            for country in matches:
                code = country["code"]
                name = country["name"]
                items.append(
                    _item(
                        name,
                        f"Connect to fastest in {name} or choose a city  [{code}]",
                        Utils.flag_path(code),
                        _action_keep(
                            {
                                "action": ACT_SHOW_CITIES,
                                "code": code,
                                "name": name,
                            }
                        ),
                    )
                )

        return items

    def _city_screen(self, pvpn, country_code, country_name, max_entries):
        """Build the city picker for a selected country."""
        flag = Utils.flag_path(country_code)
        icon = Utils.get_path("images/icon.svg")

        items = [
            _item(
                f"Fastest server in {country_name}",
                f"Connect to the fastest available server in {country_name}",
                flag,
                _action({"action": ACT_CONNECT_COUNTRY, "code": country_code}),
            )
        ]

        if not pvpn.has_cities(country_code):
            # Cities not cached yet — trigger a background fetch and show a
            # placeholder.  Next time the user opens this country it will be instant.
            _run_in_background(lambda: pvpn.fetch_cities(country_code))
            items.append(
                _item(
                    "Loading cities…",
                    "Cities are being fetched. Select again in a moment.",
                    icon,
                    _action_keep(
                        {
                            "action": ACT_SHOW_CITIES,
                            "code": country_code,
                            "name": country_name,
                        }
                    ),
                )
            )
            return items

        cities = pvpn.get_cities(country_code)
        if cities:
            for city in cities[: max_entries - 1]:
                name = city["name"]
                features = city.get("features", "")
                desc = (
                    f"Features: {features}"
                    if features
                    else f"Connect to {name}, {country_code}"
                )
                items.append(
                    _item(
                        name,
                        desc,
                        flag,
                        _action(
                            {
                                "action": ACT_CONNECT_CITY,
                                "code": country_code,
                                "city": name,
                            }
                        ),
                    )
                )
        else:
            items.append(
                _item(
                    "No cities available",
                    f"Only fastest-server connection is available for {country_code}",
                    flag,
                    HideWindowAction(),
                )
            )

        return items


# ---------------------------------------------------------------------------
# ItemEnterEventListener
# ---------------------------------------------------------------------------


class ItemEnterEventListener(EventListener):
    """Handle selected result items and run long operations asynchronously."""

    def on_event(self, event, extension):
        """Execute the action stored in the selected result item's data."""
        data = event.get_data()
        action = data.get("action")
        pvpn = extension.pvpn
        max_entries = extension.max_entries

        if action == ACT_SHOW_CONNECT:
            # Re-render the connect screen with no filter — user will type to filter.
            listener = KeywordQueryEventListener()
            return RenderResultListAction(
                listener._connect_screen(pvpn, "", max_entries)
            )

        if action == ACT_SHOW_CITIES:
            code = data.get("code", "")
            name = data.get("name", code)
            listener = KeywordQueryEventListener()
            return RenderResultListAction(
                listener._city_screen(pvpn, code, name, max_entries)
            )

        if action == ACT_CONNECT_FASTEST:

            def _do_connect():
                success, ip = pvpn.connect()
                message = (
                    (f"Connected. IP: {ip}" if ip else "Connected.")
                    if success
                    else "Connection failed."
                )
                Utils.notify(
                    "ProtonVPN",
                    message,
                )

            _run_in_background(_do_connect)
            Utils.notify("ProtonVPN", "Connecting to fastest server…")
            return HideWindowAction()

        if action == ACT_CONNECT_COUNTRY:
            code = data.get("code")

            def _do_connect():
                success, ip = pvpn.connect(country_code=code)
                message = (
                    (
                        f"Connected to {code}. IP: {ip}"
                        if ip
                        else f"Connected to {code}."
                    )
                    if success
                    else f"Connection to {code} failed."
                )
                Utils.notify(
                    "ProtonVPN",
                    message,
                )

            _run_in_background(_do_connect)
            Utils.notify("ProtonVPN", f"Connecting to {code}…")
            return HideWindowAction()

        if action == ACT_CONNECT_CITY:
            code = data.get("code")
            city = data.get("city")

            def _do_connect():
                success, ip = pvpn.connect(country_code=code, city=city)
                message = (
                    (
                        f"Connected to {city}, {code}. IP: {ip}"
                        if ip
                        else f"Connected to {city}, {code}."
                    )
                    if success
                    else f"Connection to {city}, {code} failed."
                )
                Utils.notify(
                    "ProtonVPN",
                    message,
                )

            _run_in_background(_do_connect)
            Utils.notify("ProtonVPN", f"Connecting to {city}, {code}…")
            return HideWindowAction()

        if action == ACT_DISCONNECT:

            def _do_disconnect():
                success = pvpn.disconnect()
                message = (
                    "Disconnected."
                    if success
                    else "Disconnect failed or already disconnected."
                )
                Utils.notify("ProtonVPN", message)

            _run_in_background(_do_disconnect)
            Utils.notify("ProtonVPN", "Disconnecting…")
            return HideWindowAction()

        if action == ACT_REFRESH:

            def _do_refresh():
                success = pvpn.refresh_cache()
                if success:
                    country_count = len(pvpn.get_countries())
                    Utils.notify(
                        "ProtonVPN",
                        f"Server list saved. {country_count} countries available.",
                    )
                else:
                    Utils.notify(
                        "ProtonVPN",
                        "Refresh failed. Check that protonvpn CLI is signed in.",
                    )

            _run_in_background(_do_refresh)
            Utils.notify("ProtonVPN", "Fetching server list in the background…")
            return HideWindowAction()

        return HideWindowAction()


# ---------------------------------------------------------------------------
# Preferences listeners
# ---------------------------------------------------------------------------


class PreferencesEventListener(EventListener):
    """Load initial Ulauncher preference values into the extension."""

    def on_event(self, event, extension):
        """Apply keyword and max-entry preferences during extension startup."""
        extension.keyword = event.preferences.get("pvpn_kw", "pvpn")
        try:
            extension.max_entries = int(event.preferences.get("pvpn_max_entry", "10"))
        except ValueError:
            extension.max_entries = 10


class PreferencesUpdateEventListener(EventListener):
    """Keep extension settings in sync when Ulauncher preferences change."""

    def on_event(self, event, extension):
        """Apply a single changed preference value to the running extension."""
        if event.id == "pvpn_kw":
            extension.keyword = event.new_value
        elif event.id == "pvpn_max_entry":
            try:
                extension.max_entries = int(event.new_value)
            except ValueError:
                pass
