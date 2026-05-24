"""Tests for src/listeners.py — KeywordQueryEventListener routing."""

import threading
from unittest.mock import MagicMock, patch

from src.listeners import (
    ACT_CONNECT_CITY,
    ACT_CONNECT_COUNTRY,
    ACT_CONNECT_FASTEST,
    ACT_DISCONNECT,
    ACT_REFRESH,
    ACT_SHOW_CITIES,
    ACT_SHOW_CONNECT,
    ItemEnterEventListener,
    KeywordQueryEventListener,
    PreferencesEventListener,
    PreferencesUpdateEventListener,
    _refresh_status_soon,
    _run_in_background,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COUNTRIES = [
    {"name": "United States", "code": "US"},
    {"name": "Germany", "code": "DE"},
    {"name": "Netherlands", "code": "NL"},
]

CITIES_US = [
    {"name": "New York", "features": "P2P"},
    {"name": "Atlanta", "features": "P2P, Tor"},
]


def _make_extension(query="", status=None, has_cache=True):
    pvpn = MagicMock()
    pvpn.get_status.return_value = status
    pvpn.get_countries.return_value = COUNTRIES
    pvpn.get_cities.return_value = CITIES_US
    pvpn.has_cache.return_value = has_cache

    ext = MagicMock()
    ext.pvpn = pvpn
    ext.keyword = "pvpn"
    ext.max_entries = 10

    event = MagicMock()
    event.get_argument.return_value = query

    return ext, event


def _item_names(result):
    return [item.get_name() for item in result.result_list]


def _item_descriptions(result):
    return [item.get_description("") for item in result.result_list]


# ---------------------------------------------------------------------------
# Home screen
# ---------------------------------------------------------------------------


class TestHomeScreen:
    def test_empty_query_shows_home_disconnected(self):
        ext, event = _make_extension(query="")
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("fastest" in n.lower() for n in names)
        assert any("country" in n.lower() for n in names)
        assert any("refresh" in n.lower() or "Fetch" in n for n in names)

    def test_connected_home_shows_server_and_disconnect(self):
        status = {
            "server": "NL#42",
            "load": "29%",
            "protocol": "wireguard",
            "ip": None,
        }
        ext, event = _make_extension(query="", status=status)
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("Connected" in n for n in names)
        assert any("Disconnect" in n for n in names)

    def test_connected_home_no_connect_items(self):
        status = {
            "server": "DE#5",
            "load": "10%",
            "protocol": "openvpn",
            "ip": "1.2.3.4",
        }
        ext, event = _make_extension(query="", status=status)
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert not any("fastest" in n.lower() for n in names)
        assert not any("country" in n.lower() for n in names)

    def test_connected_home_hides_none_status_fields(self):
        status = {
            "server": "NL#42",
            "load": None,
            "protocol": None,
            "ip": None,
        }
        ext, event = _make_extension(query="", status=status)
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        descriptions = _item_descriptions(result)
        assert any("Load: ?" in d for d in descriptions)
        assert any("Protocol: ?" in d for d in descriptions)
        assert not any("None" in d for d in descriptions)

    def test_home_shows_fetch_when_no_cache(self):
        ext, event = _make_extension(query="", has_cache=False)
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("Refresh" in n for n in names)


# ---------------------------------------------------------------------------
# Connect screen (typed query filters countries)
# ---------------------------------------------------------------------------


class TestConnectScreen:
    def test_typed_query_filters_countries(self):
        ext, event = _make_extension(query="ger")
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("Germany" in n for n in names)
        assert not any("United States" in n for n in names)

    def test_typed_query_shows_matching_countries(self):
        ext, event = _make_extension(query="us")
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("United States" in n for n in names)

    def test_no_match_shows_not_found(self):
        ext, event = _make_extension(query="zzz")
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("No countries found" in n for n in names)

    def test_empty_country_cache_prompts_refresh(self):
        ext, event = _make_extension(query="ger", has_cache=False)
        ext.pvpn.get_countries.return_value = []
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("Server list not available" in n for n in names)
        assert not any("No countries found" in n for n in names)


# ---------------------------------------------------------------------------
# City screen (via ItemEnterEventListener ACT_SHOW_CITIES)
# ---------------------------------------------------------------------------


class TestCityScreen:
    def _enter_event(self, data, ext):
        event = MagicMock()
        event.get_data.return_value = data
        return event

    def test_show_cities_renders_city_screen(self):
        ext, _ = _make_extension()
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_SHOW_CITIES, "code": "US"}, ext)
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("Fastest" in n for n in names)
        assert any("New York" in n for n in names)

    def test_city_screen_no_cities_shows_fallback(self):
        ext, _ = _make_extension()
        ext.pvpn.get_cities.return_value = []
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_SHOW_CITIES, "code": "DE"}, ext)
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("No cities" in n for n in names)

    def test_city_screen_shows_loading_when_cities_not_cached(self):
        ext, _ = _make_extension()
        ext.pvpn.has_cities.return_value = False
        listener = ItemEnterEventListener()
        event = self._enter_event(
            {"action": ACT_SHOW_CITIES, "code": "NL", "name": "Netherlands"}, ext
        )
        with patch("src.listeners.Utils"), patch("src.listeners._run_in_background"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("Fastest" in n for n in names)
        assert any("Loading" in n for n in names)

    def test_show_connect_renders_full_country_list(self):
        ext, _ = _make_extension()
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_SHOW_CONNECT}, ext)
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("United States" in n for n in names)
        assert any("Germany" in n for n in names)


# ---------------------------------------------------------------------------
# Connect actions
# ---------------------------------------------------------------------------


class TestConnectActions:
    def _enter_event(self, data):
        event = MagicMock()
        event.get_data.return_value = data
        return event

    def test_successful_connect_schedules_status_refresh(self):
        ext, _ = _make_extension()
        ext.pvpn.connect.return_value = (True, "146.70.98.133")
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_CONNECT_FASTEST})

        with (
            patch("src.listeners.Utils"),
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
            patch("src.listeners._refresh_status_soon") as mock_refresh_status,
        ):
            listener.on_event(event, ext)

        ext.pvpn.connect.assert_called_once_with()
        mock_refresh_status.assert_called_once_with(ext.pvpn)
        ext.pvpn.get_status.assert_not_called()

    def test_connect_fastest_success_without_ip(self):
        ext, _ = _make_extension()
        ext.pvpn.connect.return_value = (True, None)
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_CONNECT_FASTEST})

        with (
            patch("src.listeners.Utils") as mock_utils,
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
            patch("src.listeners._refresh_status_soon"),
        ):
            listener.on_event(event, ext)

        calls = [str(c) for c in mock_utils.notify.call_args_list]
        assert any("Connected." in c for c in calls)

    def test_connect_fastest_failure(self):
        ext, _ = _make_extension()
        ext.pvpn.connect.return_value = (False, None)
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_CONNECT_FASTEST})

        with (
            patch("src.listeners.Utils") as mock_utils,
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
            patch("src.listeners._refresh_status_soon") as mock_refresh,
        ):
            listener.on_event(event, ext)

        calls = [str(c) for c in mock_utils.notify.call_args_list]
        assert any("failed" in c for c in calls)
        mock_refresh.assert_not_called()

    def test_connect_country_success(self):
        ext, _ = _make_extension()
        ext.pvpn.connect.return_value = (True, "1.2.3.4")
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_CONNECT_COUNTRY, "code": "NL"})

        with (
            patch("src.listeners.Utils"),
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
            patch("src.listeners._refresh_status_soon") as mock_refresh,
        ):
            listener.on_event(event, ext)

        ext.pvpn.connect.assert_called_once_with(country_code="NL")
        mock_refresh.assert_called_once_with(ext.pvpn)

    def test_connect_country_failure(self):
        ext, _ = _make_extension()
        ext.pvpn.connect.return_value = (False, None)
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_CONNECT_COUNTRY, "code": "NL"})

        with (
            patch("src.listeners.Utils") as mock_utils,
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
            patch("src.listeners._refresh_status_soon") as mock_refresh,
        ):
            listener.on_event(event, ext)

        calls = [str(c) for c in mock_utils.notify.call_args_list]
        assert any("failed" in c for c in calls)
        mock_refresh.assert_not_called()

    def test_connect_city_success(self):
        ext, _ = _make_extension()
        ext.pvpn.connect.return_value = (True, "1.2.3.4")
        listener = ItemEnterEventListener()
        event = self._enter_event(
            {"action": ACT_CONNECT_CITY, "code": "NL", "city": "Amsterdam"}
        )

        with (
            patch("src.listeners.Utils"),
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
            patch("src.listeners._refresh_status_soon") as mock_refresh,
        ):
            listener.on_event(event, ext)

        ext.pvpn.connect.assert_called_once_with(country_code="NL", city="Amsterdam")
        mock_refresh.assert_called_once_with(ext.pvpn)

    def test_connect_city_failure(self):
        ext, _ = _make_extension()
        ext.pvpn.connect.return_value = (False, None)
        listener = ItemEnterEventListener()
        event = self._enter_event(
            {"action": ACT_CONNECT_CITY, "code": "NL", "city": "Amsterdam"}
        )

        with (
            patch("src.listeners.Utils") as mock_utils,
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
            patch("src.listeners._refresh_status_soon") as mock_refresh,
        ):
            listener.on_event(event, ext)

        calls = [str(c) for c in mock_utils.notify.call_args_list]
        assert any("failed" in c for c in calls)
        mock_refresh.assert_not_called()

    def test_disconnect_success(self):
        ext, _ = _make_extension()
        ext.pvpn.disconnect.return_value = True
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_DISCONNECT})

        with (
            patch("src.listeners.Utils") as mock_utils,
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
        ):
            listener.on_event(event, ext)

        calls = [str(c) for c in mock_utils.notify.call_args_list]
        assert any("Disconnected." in c for c in calls)

    def test_disconnect_failure(self):
        ext, _ = _make_extension()
        ext.pvpn.disconnect.return_value = False
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_DISCONNECT})

        with (
            patch("src.listeners.Utils") as mock_utils,
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
        ):
            listener.on_event(event, ext)

        calls = [str(c) for c in mock_utils.notify.call_args_list]
        assert any("failed" in c for c in calls)

    def test_refresh_success(self):
        ext, _ = _make_extension()
        ext.pvpn.refresh_cache.return_value = True
        ext.pvpn.get_countries.return_value = [{"name": "Netherlands", "code": "NL"}]
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_REFRESH})

        with (
            patch("src.listeners.Utils") as mock_utils,
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
        ):
            listener.on_event(event, ext)

        calls = [str(c) for c in mock_utils.notify.call_args_list]
        assert any("countries available" in c for c in calls)

    def test_refresh_failure(self):
        ext, _ = _make_extension()
        ext.pvpn.refresh_cache.return_value = False
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_REFRESH})

        with (
            patch("src.listeners.Utils") as mock_utils,
            patch(
                "src.listeners._run_in_background", side_effect=lambda target: target()
            ),
        ):
            listener.on_event(event, ext)

        calls = [str(c) for c in mock_utils.notify.call_args_list]
        assert any("Refresh failed" in c for c in calls)

    def test_unknown_action_returns_hide(self):
        ext, _ = _make_extension()
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": "UNKNOWN_ACTION"})

        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)

        from ulauncher.api.shared.action.HideWindowAction import HideWindowAction

        assert isinstance(result, HideWindowAction)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_run_in_background_executes_target(self):
        done = threading.Event()
        _run_in_background(lambda: done.set())
        assert done.wait(timeout=2.0)

    def test_refresh_status_soon_schedules_delayed_call(self):
        pvpn = MagicMock()
        with patch("threading.Timer") as mock_timer:
            mock_timer.return_value = MagicMock()
            _refresh_status_soon(pvpn, delay=2.0)
        mock_timer.assert_called_once_with(2.0, pvpn.get_status)
        mock_timer.return_value.start.assert_called_once()


# ---------------------------------------------------------------------------
# Preferences listeners
# ---------------------------------------------------------------------------


class TestPreferencesEventListener:
    def _make_event(self, kw="pvpn", max_entry="10"):
        event = MagicMock()
        event.preferences.get.side_effect = lambda key, default: {
            "pvpn_kw": kw,
            "pvpn_max_entry": max_entry,
        }.get(key, default)
        return event

    def test_sets_keyword_and_max_entries(self):
        ext = MagicMock()
        listener = PreferencesEventListener()
        listener.on_event(self._make_event(kw="vpn", max_entry="5"), ext)
        assert ext.keyword == "vpn"
        assert ext.max_entries == 5

    def test_defaults_max_entries_on_invalid_value(self):
        ext = MagicMock()
        listener = PreferencesEventListener()
        listener.on_event(self._make_event(max_entry="bad"), ext)
        assert ext.max_entries == 10


class TestPreferencesUpdateEventListener:
    def _make_event(self, event_id, new_value):
        event = MagicMock()
        event.id = event_id
        event.new_value = new_value
        return event

    def test_updates_keyword(self):
        ext = MagicMock()
        listener = PreferencesUpdateEventListener()
        listener.on_event(self._make_event("pvpn_kw", "vpn"), ext)
        assert ext.keyword == "vpn"

    def test_updates_max_entries(self):
        ext = MagicMock()
        listener = PreferencesUpdateEventListener()
        listener.on_event(self._make_event("pvpn_max_entry", "15"), ext)
        assert ext.max_entries == 15

    def test_ignores_invalid_max_entries(self):
        ext = MagicMock()
        ext.max_entries = 10
        listener = PreferencesUpdateEventListener()
        listener.on_event(self._make_event("pvpn_max_entry", "not_a_number"), ext)
        assert ext.max_entries == 10

    def test_ignores_unknown_preference_id(self):
        ext = MagicMock()
        listener = PreferencesUpdateEventListener()
        listener.on_event(self._make_event("unknown_pref", "whatever"), ext)
        # No crash and no attribute set
        ext.keyword = getattr(ext, "keyword", None)
