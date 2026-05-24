from typing import Any


class ExtensionResultItem:
    def __init__(
        self,
        icon: str,
        name: str,
        description: str,
        on_enter: Any,
    ) -> None: ...
    def get_name(self) -> str: ...
