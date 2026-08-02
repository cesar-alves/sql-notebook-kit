"""Versioned frontend comm transport for cell metadata persistence."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from typing import Any

from redshift_notebooks.errors import VisualizationPersistenceError
from redshift_notebooks.visualize.models import VisualizationCollection
from redshift_notebooks.visualize.theme import ThemeContext

PROTOCOL_VERSION = 1
COMM_TARGET = "redshift_notebooks.visualizations.v1"


class CommPersistenceBridge:
    """Synchronous request facade over the notebook kernel comm channel."""

    available = False

    def __init__(self, cell_id: str, *, timeout: float = 0.75) -> None:
        self.cell_id = cell_id
        self.timeout = timeout
        self.reason: str | None = "Frontend metadata companion did not respond."
        self.theme = ThemeContext.fallback("light")
        self._theme_listeners: list[Callable[[ThemeContext], None]] = []
        self._pending: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        try:
            from comm import create_comm

            self._comm = create_comm(target_name=COMM_TARGET)
            self._comm.on_msg(self._on_message)
            result = self._request("capabilities", {})
            self.available = bool(result.get("persistence"))
            self.reason = (
                None
                if self.available
                else str(result.get("reason", "Frontend metadata persistence is unavailable."))
            )
        except Exception as exc:
            self.reason = f"Frontend metadata companion is unavailable ({type(exc).__name__})."
            self.available = False

    def _on_message(self, message: dict[str, Any]) -> None:
        data = message.get("content", {}).get("data", {})
        if data.get("operation") == "theme_changed":
            self._receive_theme(data.get("payload", {}))
            return
        request_id = data.get("request_id")
        pending = self._pending.get(request_id)
        if pending is None:
            return
        event, result = pending
        result.update(data)
        event.set()

    def _receive_theme(self, payload: dict[str, Any]) -> None:
        kind = payload.get("kind")
        if kind not in ("light", "dark", "high_contrast"):
            return
        fallback = ThemeContext.fallback(kind)
        supplied = payload.get("tokens")
        if not isinstance(supplied, dict):
            return
        tokens = {**fallback.tokens, **supplied}
        try:
            theme = ThemeContext(kind, tokens, colorway=fallback.colorway)
        except Exception:
            return
        self.theme = theme
        for listener in tuple(self._theme_listeners):
            listener(theme)

    def subscribe_theme(self, listener: Callable[[ThemeContext], None]) -> None:
        self._theme_listeners.append(listener)

    def _request(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        event = threading.Event()
        result: dict[str, Any] = {}
        self._pending[request_id] = (event, result)
        self._comm.send(
            {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request_id,
                "cell_id": self.cell_id,
                "operation": operation,
                "payload": payload,
            }
        )
        if not event.wait(self.timeout):
            self._pending.pop(request_id, None)
            raise VisualizationPersistenceError(f"Frontend {operation} request timed out.")
        self._pending.pop(request_id, None)
        if result.get("operation") == "error":
            raise VisualizationPersistenceError(str(result.get("message", "Persistence failed.")))
        return result.get("payload", result)

    def load(self) -> VisualizationCollection:
        if not self.available:
            raise VisualizationPersistenceError(self.reason or "Persistence is unavailable.")
        result = self._request("load", {})
        return VisualizationCollection.from_dict(result.get("collection", {}))

    def save(self, collection: VisualizationCollection, *, expected_revision: int) -> int:
        if not self.available:
            raise VisualizationPersistenceError(self.reason or "Persistence is unavailable.")
        result = self._request(
            "save",
            {"expected_revision": expected_revision, "collection": collection.to_dict()},
        )
        if result.get("conflict"):
            raise VisualizationPersistenceError("Visualization metadata changed in another view.")
        revision = result.get("revision")
        if not isinstance(revision, int):
            raise VisualizationPersistenceError("Frontend returned an invalid revision.")
        return revision


def create_persistence_bridge(cell_id: str | None) -> Any:
    """Create a comm bridge only while executing inside a live IPython kernel."""
    if not cell_id:
        return None
    try:
        from IPython import get_ipython

        shell = get_ipython()
        if shell is None or getattr(shell, "kernel", None) is None:
            return None
    except Exception:
        return None
    return CommPersistenceBridge(cell_id)


__all__ = ["COMM_TARGET", "PROTOCOL_VERSION", "CommPersistenceBridge"]
