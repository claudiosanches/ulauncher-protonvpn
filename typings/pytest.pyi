from collections.abc import Callable
from typing import Any


def fixture(*, autouse: bool = False) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...
