"""Tests for src/listeners.py — KeywordQueryEventListener routing."""

from unittest.mock import MagicMock, patch

from src.listeners import KeywordQueryEventListener, ItemEnterEventListener, ACT_SHOW_CITIES, ACT_SHOW_CONNECT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COUNTRIES = [
    {"name": "United States", "code": "US"},
    {"name": "Germany", "code": "DE"},
    {"name": "Brazil", "code": "BR"},
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
        status = {"server": "BR#116", "load": "29%", "protocol": "wireguard", "ip": None}
        ext, event = _make_extension(query="", status=status)
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("Connected" in n for n in names)
        assert any("Disconnect" in n for n in names)

    def test_connected_home_no_connect_items(self):
        status = {"server": "DE#5", "load": "10%", "protocol": "openvpn", "ip": "1.2.3.4"}
        ext, event = _make_extension(query="", status=status)
        listener = KeywordQueryEventListener()
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert not any("fastest" in n.lower() for n in names)
        assert not any("country" in n.lower() for n in names)

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

    def test_show_connect_renders_full_country_list(self):
        ext, _ = _make_extension()
        listener = ItemEnterEventListener()
        event = self._enter_event({"action": ACT_SHOW_CONNECT}, ext)
        with patch("src.listeners.Utils"):
            result = listener.on_event(event, ext)
        names = _item_names(result)
        assert any("United States" in n for n in names)
        assert any("Germany" in n for n in names)
