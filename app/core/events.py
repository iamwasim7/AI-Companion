"""Lightweight in-process event bus for UI and services."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any


class EventBus:
    """Simple pub/sub. Handlers must not block the UI thread for long work."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable[..., Any]) -> None:
        self._subscribers[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable[..., Any]) -> None:
        handlers = self._subscribers.get(event)
        if not handlers:
            return
        self._subscribers[event] = [item for item in handlers if item != handler]

    def emit(self, event: str, **payload: Any) -> None:
        for handler in list(self._subscribers.get(event, [])):
            handler(**payload)


bus = EventBus()
