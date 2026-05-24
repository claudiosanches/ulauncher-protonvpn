from typing import Any


class EventListener:
    def on_event(self, event: Any, extension: Any) -> Any: ...
