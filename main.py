"""ProtonVPN Ulauncher extension entry point."""

import threading

from ulauncher.api.client.Extension import Extension
from ulauncher.api.shared.event import (
    KeywordQueryEvent,
    ItemEnterEvent,
    PreferencesEvent,
    PreferencesUpdateEvent,
)

from src.protonvpn import ProtonVPN
from src.listeners import (
    KeywordQueryEventListener,
    ItemEnterEventListener,
    PreferencesEventListener,
    PreferencesUpdateEventListener,
)
from src.utils import Utils


class ProtonVPNExtension(Extension):
    """Main extension class for ProtonVPN."""

    def __init__(self):
        super().__init__()

        # Preference values — populated by PreferencesEventListener on start.
        self.keyword: str = "pvpn"
        self.max_entries: int = 10

        # Core ProtonVPN manager.
        self.pvpn = ProtonVPN()

        # Warn on startup if the CLI is not installed.
        if not self.pvpn.is_installed():
            Utils.notify(
                "ProtonVPN",
                "protonvpn CLI not found. Please install ProtonVPN CLI.",
            )

        # Kick off a background status refresh so home screen is up to date.
        # Set the flag first so get_status() doesn't spawn a second thread
        # before this one has had a chance to run.
        self.pvpn._status_refreshing = True
        threading.Thread(target=self.pvpn._refresh_status, daemon=True).start()

        # Subscribe to Ulauncher events.
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())
        self.subscribe(PreferencesEvent, PreferencesEventListener())
        self.subscribe(PreferencesUpdateEvent, PreferencesUpdateEventListener())



if __name__ == "__main__":
    ProtonVPNExtension().run()
