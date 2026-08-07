"""Versioned frontend transports for cell metadata persistence."""

from __future__ import annotations

import base64
import json
import threading
import uuid
import weakref
from collections.abc import Callable
from typing import Any

from sql_notebook_kit.errors import VisualizationPersistenceError
from sql_notebook_kit.visualize.models import VisualizationCollection
from sql_notebook_kit.visualize.theme import ThemeContext

PROTOCOL_VERSION = 1
COMM_TARGET = "sql_notebook_kit.visualizations.v1"
VSCODE_MIME = "application/vnd.sql-notebook-kit.bridge+json"
VSCODE_CAPABILITY_TIMEOUT = 45.0
_VSCODE_BRIDGES: weakref.WeakValueDictionary[str, VscodePersistenceBridge] = (
    weakref.WeakValueDictionary()
)


class _ThemeSupport:
    theme: ThemeContext

    def _init_theme(self) -> None:
        self.theme = ThemeContext.fallback("light")
        self._theme_listeners: list[Callable[[ThemeContext], None]] = []

    def subscribe_theme(self, listener: Callable[[ThemeContext], None]) -> None:
        self._theme_listeners.append(listener)

    def _receive_theme(self, payload: dict[str, Any]) -> None:
        kind = payload.get("kind")
        if kind not in ("light", "dark", "high_contrast"):
            return
        fallback = ThemeContext.fallback(kind)
        supplied = payload.get("tokens")
        if not isinstance(supplied, dict):
            return
        try:
            self.theme = ThemeContext(
                kind, {**fallback.tokens, **supplied}, colorway=fallback.colorway
            )
        except Exception:
            return
        for listener in tuple(self._theme_listeners):
            listener(self.theme)


class CommPersistenceBridge(_ThemeSupport):
    """Synchronous JupyterLab request facade over a kernel comm."""

    deferred = False
    available = False

    def __init__(self, cell_id: str, *, timeout: float = 1.5) -> None:
        self.cell_id = cell_id
        self.session_id = str(uuid.uuid4())
        self.timeout = timeout
        self.reason: str | None = "Frontend metadata companion did not respond."
        self._init_theme()
        self._pending: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        try:
            from comm import create_comm

            self._comm = create_comm(target_name=COMM_TARGET)
            self._comm.on_msg(self._on_message)
            result = self._request("capabilities", {})
            self.available = bool(result.get("persistence"))
            self.reason = None if self.available else str(
                result.get("reason", "Frontend metadata persistence is unavailable.")
            )
        except Exception as exc:
            self.reason = f"Frontend metadata companion is unavailable ({type(exc).__name__})."

    def _on_message(self, message: dict[str, Any]) -> None:
        data = message.get("content", {}).get("data", {})
        if not isinstance(data, dict):
            return
        if data.get("session_id") != self.session_id:
            return
        if data.get("operation") == "theme_changed":
            self._receive_theme(data.get("payload", {}))
            return
        request_id = data.get("request_id")
        if not isinstance(request_id, str):
            return
        pending = self._pending.get(request_id)
        if pending:
            pending[1].update(data)
            pending[0].set()

    def _request(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        event = threading.Event()
        result: dict[str, Any] = {}
        self._pending[request_id] = (event, result)
        self._comm.send(self._message(request_id, operation, payload))
        if not event.wait(self.timeout):
            self._pending.pop(request_id, None)
            raise VisualizationPersistenceError(f"Frontend {operation} request timed out.")
        self._pending.pop(request_id, None)
        if result.get("operation") == "error":
            error_payload = result.get("payload", {})
            raise VisualizationPersistenceError(
                str(error_payload.get("message", "Persistence failed."))
            )
        return result.get("payload", {})

    def _message(self, request_id: str, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "session_id": self.session_id,
            "cell_id": self.cell_id,
            "operation": operation,
            "payload": payload,
        }

    def load(self) -> VisualizationCollection:
        return VisualizationCollection.from_dict(self._request("load", {}).get("collection", {}))

    def save(self, collection: VisualizationCollection, *, expected_revision: int) -> int:
        result = self._request("save", {
            "expected_revision": expected_revision, "collection": collection.to_dict()
        })
        if result.get("conflict"):
            raise VisualizationPersistenceError("Visualization metadata changed in another view.")
        revision = result.get("revision")
        if not isinstance(revision, int):
            raise VisualizationPersistenceError("Frontend returned an invalid revision.")
        return revision


class VscodePersistenceBridge(_ThemeSupport):
    """Deferred renderer bridge used by VS Code's Jupyter notebook frontend."""

    deferred = True
    available = False

    def __init__(self, cell_id: str) -> None:
        self.cell_id = cell_id
        self.session_id = str(uuid.uuid4())
        self.reason: str | None = "Connecting to the VS Code metadata companion."
        self._init_theme()
        self._handler: Callable[[dict[str, Any]], None] | None = None
        self._state_handler: Callable[[], None] | None = None
        self._display_id = f"sql-notebook-kit-{self.session_id}"
        _VSCODE_BRIDGES[self.session_id] = self
        self._emit("capabilities", {})
        self._capability_timer = threading.Timer(
            VSCODE_CAPABILITY_TIMEOUT, self._capability_timeout
        )
        self._capability_timer.daemon = True
        self._capability_timer.start()

    def set_response_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._handler = handler

    def subscribe_state(self, handler: Callable[[], None]) -> None:
        self._state_handler = handler

    def load(self) -> VisualizationCollection:
        raise VisualizationPersistenceError(
            "VS Code state is loaded from execute-request metadata."
        )

    def save(self, collection: VisualizationCollection, *, expected_revision: int) -> None:
        self._emit("save", {
            "expected_revision": expected_revision, "collection": collection.to_dict()
        })

    def _emit(self, operation: str, payload: dict[str, Any]) -> None:
        from IPython.display import display, update_display

        message = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "cell_id": self.cell_id,
            "operation": operation,
            "payload": payload,
        }
        if operation == "capabilities":
            display({VSCODE_MIME: message}, raw=True, display_id=self._display_id)
        else:
            update_display({VSCODE_MIME: message}, raw=True, display_id=self._display_id)

    def _receive(self, message: dict[str, Any]) -> None:
        operation = message.get("operation")
        payload = message.get("payload", {})
        if operation == "theme_changed":
            self._receive_theme(payload)
            return
        if operation == "capabilities_result":
            self._capability_timer.cancel()
            self.available = bool(payload.get("persistence"))
            self.reason = None if self.available else str(
                payload.get("reason", "VS Code metadata persistence is unavailable.")
            )
            if self._state_handler:
                self._state_handler()
        if self._handler:
            self._handler(message)
        self._neutralize(message)

    def _capability_timeout(self) -> None:
        if self.available:
            return
        self.reason = "VS Code metadata companion did not respond."
        if self._state_handler:
            self._state_handler()

    def _neutralize(self, message: dict[str, Any]) -> None:
        from IPython.display import update_display

        idle = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": message.get("request_id", str(uuid.uuid4())),
            "session_id": self.session_id,
            "cell_id": self.cell_id,
            "operation": "save_result",
            "payload": {"idle": True},
        }
        update_display({VSCODE_MIME: idle}, raw=True, display_id=self._display_id)


def _deliver_vscode_response(encoded: str) -> None:
    """Receive a trusted callback emitted through the stable VS Code Jupyter API."""
    try:
        message = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
        if not isinstance(message, dict):
            return
        if message.get("protocol_version") != PROTOCOL_VERSION:
            return
        session_id = message.get("session_id")
        if not isinstance(session_id, str):
            return
        bridge = _VSCODE_BRIDGES.get(session_id)
        if bridge is not None:
            bridge._receive(message)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return


def create_persistence_bridge(cell_id: str | None) -> Any:
    if not cell_id:
        return None
    try:
        from IPython import get_ipython

        shell = get_ipython()
        if shell is None or getattr(shell, "kernel", None) is None:
            return None
    except Exception:
        return None
    if cell_id.startswith("vscode-notebook-cell:"):
        return VscodePersistenceBridge(cell_id)
    return CommPersistenceBridge(cell_id)


__all__ = ["COMM_TARGET", "PROTOCOL_VERSION", "CommPersistenceBridge", "VSCODE_MIME"]
