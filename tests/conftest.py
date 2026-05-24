"""Test shims for Ulauncher and PyGObject runtime modules."""

import importlib.util
import sys
from types import ModuleType
from typing import Any


def _module(name: str, *, package: bool = False) -> ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = ModuleType(name)
        sys.modules[name] = mod
    if package:
        mod.__path__ = []  # type: ignore[attr-defined]
    if "." in name:
        parent_name, attr = name.rsplit(".", 1)
        parent = _module(parent_name, package=True)
        setattr(parent, attr, mod)
    return mod


def _install_gi_shim() -> None:
    gi = _module("gi", package=True)
    repository = _module("gi.repository", package=True)
    notify = _module("gi.repository.Notify")

    def require_version(namespace: str, version: str) -> None:
        return None

    class Notification:
        @classmethod
        def new(cls, title: str, message: str, icon: str) -> "Notification":
            return cls()

        def set_timeout(self, timeout: int) -> None:
            return None

        def show(self) -> bool:
            return True

    def init(app_name: str) -> bool:
        return True

    setattr(gi, "require_version", require_version)
    setattr(notify, "init", init)
    setattr(notify, "Notification", Notification)
    setattr(repository, "Notify", notify)


def _install_ulauncher_shim() -> None:
    class Extension:
        def subscribe(self, event_type: type, listener: Any) -> None:
            return None

        def run(self) -> None:
            return None

    class EventListener:
        def on_event(self, event: Any, extension: Any) -> Any:
            return None

    class ExtensionCustomAction:
        def __init__(self, data: dict[str, Any], keep_app_open: bool = False) -> None:
            self.data = data
            self.keep_app_open = keep_app_open

    class HideWindowAction:
        pass

    class RenderResultListAction:
        def __init__(self, result_list: list[Any]) -> None:
            self.result_list = result_list

    class ExtensionResultItem:
        def __init__(
            self,
            icon: str,
            name: str,
            description: str,
            on_enter: Any,
        ) -> None:
            self.icon = icon
            self.name = name
            self.description = description
            self.on_enter = on_enter

        def get_name(self) -> str:
            return self.name

        def get_description(self, query: str = "") -> str:
            return self.description

    class KeywordQueryEvent:
        pass

    class ItemEnterEvent:
        pass

    class PreferencesEvent:
        pass

    class PreferencesUpdateEvent:
        pass

    extension_mod = _module("ulauncher.api.client.Extension")
    event_listener_mod = _module("ulauncher.api.client.EventListener")
    custom_action_mod = _module("ulauncher.api.shared.action.ExtensionCustomAction")
    hide_action_mod = _module("ulauncher.api.shared.action.HideWindowAction")
    render_action_mod = _module("ulauncher.api.shared.action.RenderResultListAction")
    event_mod = _module("ulauncher.api.shared.event")
    item_mod = _module("ulauncher.api.shared.item.ExtensionResultItem")

    setattr(extension_mod, "Extension", Extension)
    setattr(event_listener_mod, "EventListener", EventListener)
    setattr(custom_action_mod, "ExtensionCustomAction", ExtensionCustomAction)
    setattr(hide_action_mod, "HideWindowAction", HideWindowAction)
    setattr(render_action_mod, "RenderResultListAction", RenderResultListAction)
    setattr(event_mod, "KeywordQueryEvent", KeywordQueryEvent)
    setattr(event_mod, "ItemEnterEvent", ItemEnterEvent)
    setattr(event_mod, "PreferencesEvent", PreferencesEvent)
    setattr(event_mod, "PreferencesUpdateEvent", PreferencesUpdateEvent)
    setattr(item_mod, "ExtensionResultItem", ExtensionResultItem)


if importlib.util.find_spec("gi") is None:
    _install_gi_shim()

if importlib.util.find_spec("ulauncher") is None:
    _install_ulauncher_shim()
