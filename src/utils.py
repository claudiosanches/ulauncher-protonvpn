"""Utility helpers for the ProtonVPN Ulauncher extension."""

import pathlib

import gi

gi.require_version("Notify", "0.7")
from gi.repository import Notify  # noqa: E402


class Utils:
    """Utility class providing helper methods for the ProtonVPN extension."""

    @staticmethod
    def get_path(filename: str) -> str:
        """
        Return the absolute path to a file relative to the extension root.

        Args:
            filename: The name or relative path of the file.

        Returns:
            The absolute path to the file.
        """
        # __file__ is src/utils.py → parent is src/ → parent.parent is root.
        current_dir = pathlib.Path(__file__).parent.parent.absolute()
        return str(current_dir / filename)

    @staticmethod
    def notify(title: str, message: str) -> None:
        """
        Display a system desktop notification.

        Args:
            title:   The notification title.
            message: The notification body.
        """
        Notify.init("ProtonVPN")
        notification = Notify.Notification.new(
            title,
            message,
            Utils.get_path("images/icon.svg"),
        )
        notification.set_timeout(1000)
        notification.show()

    @staticmethod
    def flag_path(country_code: str) -> str:
        """
        Return the absolute path to the flag SVG for *country_code*.

        Falls back to the extension icon when the flag is not found.

        Args:
            country_code: Two-letter ISO 3166-1 alpha-2 code (e.g. "US").

        Returns:
            Absolute path to the flag SVG file.
        """
        flag_file = Utils.get_path(f"images/flags/{country_code.lower()}.svg")
        if pathlib.Path(flag_file).exists():
            return flag_file
        return Utils.get_path("images/icon.svg")
