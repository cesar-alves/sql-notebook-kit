"""In-memory visualization collection management and persistence boundary."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Protocol

from sql_notebook_kit.errors import VisualizationConfigError, VisualizationPersistenceError
from sql_notebook_kit.visualize.models import (
    MAX_ITEMS,
    VisualizationCollection,
    VisualizationSpec,
    clone_spec,
)


class PersistenceBridge(Protocol):
    available: bool
    deferred: bool
    reason: str | None

    def load(self) -> VisualizationCollection: ...

    def save(self, collection: VisualizationCollection, *, expected_revision: int) -> int: ...


class SessionPersistenceBridge:
    """Explicit session-only fallback used when no frontend companion responds."""

    available: bool = False
    deferred: bool = False
    reason: str | None

    def __init__(self, reason: str = "Frontend metadata companion is unavailable.") -> None:
        self.reason = reason

    def save(self, collection: VisualizationCollection, *, expected_revision: int) -> int:
        raise VisualizationPersistenceError(self.reason)

    def load(self) -> VisualizationCollection:
        raise VisualizationPersistenceError(self.reason)


class VisualizationManager:
    """Manage one result's applied, serializable visualization collection."""

    def __init__(
        self,
        result: Any,
        collection: VisualizationCollection | None = None,
        bridge: PersistenceBridge | None = None,
    ) -> None:
        self._result = result
        self._listeners: list[Callable[[], None]] = []
        self._in_flight: VisualizationCollection | None = None
        self._queued: VisualizationCollection | None = None
        self._conflict_draft: VisualizationCollection | None = None
        metadata = getattr(result, "visualization_metadata", None)
        metadata_error: str | None = None
        if collection is None and metadata is not None:
            try:
                collection = VisualizationCollection.from_dict(metadata)
            except VisualizationConfigError as exc:
                metadata_error = f"Stored visualization metadata is incompatible: {exc}"
        if bridge is None:
            from sql_notebook_kit.visualize.protocol import create_persistence_bridge

            bridge = create_persistence_bridge(getattr(result, "cell_id", None))
        if metadata_error:
            bridge = SessionPersistenceBridge(metadata_error)
        self._bridge = bridge or SessionPersistenceBridge()
        if (
            collection is None
            and self._bridge.available
            and not getattr(self._bridge, "deferred", False)
        ):
            try:
                collection = self._bridge.load()
            except VisualizationPersistenceError:
                collection = None
        self._collection = collection or VisualizationCollection()
        self.dirty = False
        self.persistence_error: str | None = self._bridge.reason
        set_handler = getattr(self._bridge, "set_response_handler", None)
        if set_handler is not None:
            set_handler(self._handle_bridge_response)
        subscribe_state = getattr(self._bridge, "subscribe_state", None)
        if subscribe_state is not None:
            subscribe_state(self._notify)

    @property
    def collection(self) -> VisualizationCollection:
        return self._collection

    @property
    def persistence_available(self) -> bool:
        return self._bridge.available

    @property
    def persistence_state(self) -> str:
        if self._conflict_draft is not None:
            return "conflict"
        if self.persistence_error and self.persistence_error.startswith("Connecting to"):
            return "connecting"
        if self.persistence_error:
            return "session_only"
        if self.dirty:
            return "pending"
        return "saved" if self.persistence_available else "connecting"

    def subscribe_state(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _notify(self) -> None:
        if not self._bridge.available:
            self.persistence_error = self._bridge.reason
        for listener in tuple(self._listeners):
            listener()

    def list(self) -> tuple[VisualizationSpec, ...]:
        return self._collection.items

    def get(self, id_or_name: str) -> VisualizationSpec:
        for item in self._collection.items:
            if item.id == id_or_name:
                return item
        matches = [item for item in self._collection.items if item.name == id_or_name]
        if not matches:
            raise VisualizationConfigError("visualization was not found", path="id_or_name")
        if len(matches) > 1:
            raise VisualizationConfigError("name is ambiguous; use the UUID", path="id_or_name")
        return matches[0]

    def _commit(
        self, items: tuple[VisualizationSpec, ...], active_id: str | None, persist: bool
    ) -> None:
        previous_revision = self._collection.revision
        next_collection = VisualizationCollection(1, previous_revision + 1, active_id, items)
        self._collection = next_collection
        if not persist:
            return
        if getattr(self._bridge, "deferred", False):
            self.dirty = True
            self.persistence_error = None
            if self._in_flight is None:
                self._send_deferred(next_collection, previous_revision)
            else:
                self._queued = next_collection
            self._notify()
            return
        try:
            revision = self._bridge.save(next_collection, expected_revision=previous_revision)
        except VisualizationPersistenceError as exc:
            self.dirty = True
            self.persistence_error = str(exc)
        else:
            self._collection = replace(next_collection, revision=revision)
            self.dirty = False
            self.persistence_error = None
        self._notify()

    def _send_deferred(self, collection: VisualizationCollection, expected_revision: int) -> None:
        normalized = replace(collection, revision=expected_revision + 1)
        self._in_flight = normalized
        self._bridge.save(normalized, expected_revision=expected_revision)

    def _handle_bridge_response(self, message: dict[str, Any]) -> None:
        operation = message.get("operation")
        payload = message.get("payload", {})
        if operation == "capabilities_result":
            self.persistence_error = self._bridge.reason
            self._notify()
            return
        if operation == "error":
            self._in_flight = None
            self.dirty = True
            self.persistence_error = str(payload.get("message", "Persistence failed."))
            self._notify()
            return
        if operation != "save_result" or self._in_flight is None:
            return
        attempted = self._queued or self._in_flight
        if payload.get("conflict"):
            try:
                current = VisualizationCollection.from_dict(payload.get("collection", {}))
            except VisualizationConfigError as exc:
                self.persistence_error = f"Invalid conflict response: {exc}"
            else:
                self._conflict_draft = attempted
                self._collection = current
                self.persistence_error = "Visualization metadata changed in another view."
            self._in_flight = None
            self._queued = None
            self.dirty = True
            self._notify()
            return
        revision = payload.get("revision")
        if not isinstance(revision, int):
            self.persistence_error = "Frontend returned an invalid revision."
            self._in_flight = None
            self.dirty = True
            self._notify()
            return
        self._in_flight = None
        if self._queued is not None:
            queued = self._queued
            self._queued = None
            self._collection = replace(queued, revision=revision + 1)
            self._send_deferred(self._collection, revision)
        else:
            self._collection = replace(self._collection, revision=revision)
            self.dirty = False
            self.persistence_error = None
        self._notify()

    def reapply(self) -> None:
        if self._conflict_draft is None:
            return
        draft = self._conflict_draft
        self._conflict_draft = None
        self._commit(draft.items, draft.active_id, True)

    @staticmethod
    def _unique_name(name: str, items: tuple[VisualizationSpec, ...]) -> str:
        existing = {item.name for item in items}
        if name not in existing:
            return name
        suffix = 2
        while f"{name} {suffix}" in existing:
            suffix += 1
        return f"{name} {suffix}"

    def add(self, spec: VisualizationSpec, *, persist: bool = True) -> VisualizationSpec:
        if len(self._collection.items) >= MAX_ITEMS:
            raise VisualizationConfigError(
                f"at most {MAX_ITEMS} visualizations are allowed", path="items"
            )
        if any(item.id == spec.id for item in self._collection.items):
            raise VisualizationConfigError("ID already exists", path="id")
        if any(item.name == spec.name for item in self._collection.items):
            raise VisualizationConfigError("name already exists", path="name")
        self._commit((*self._collection.items, spec), spec.id, persist)
        return spec

    def update(self, spec: VisualizationSpec, *, persist: bool = True) -> VisualizationSpec:
        current = self.get(spec.id)
        if any(item.id != current.id and item.name == spec.name for item in self._collection.items):
            raise VisualizationConfigError("name already exists", path="name")
        items = tuple(spec if item.id == current.id else item for item in self._collection.items)
        self._commit(items, spec.id, persist)
        return spec

    def rename(self, id_or_name: str, name: str, *, persist: bool = True) -> VisualizationSpec:
        current = self.get(id_or_name)
        renamed = clone_spec(current, name=name)
        return self.update(renamed, persist=persist)

    def duplicate(self, id_or_name: str, *, persist: bool = True) -> VisualizationSpec:
        source = self.get(id_or_name)
        base = f"{source.name} copy"
        name = self._unique_name(base, self._collection.items)
        duplicate = clone_spec(source, id=str(uuid.uuid4()), name=name)
        position = self._collection.items.index(source) + 1
        items = self._collection.items[:position] + (duplicate,) + self._collection.items[position:]
        self._commit(items, duplicate.id, persist)
        return duplicate

    def delete(self, id_or_name: str, *, persist: bool = True) -> None:
        source = self.get(id_or_name)
        index = self._collection.items.index(source)
        items = tuple(item for item in self._collection.items if item.id != source.id)
        if self._collection.active_id == source.id:
            active_id = items[index - 1].id if items and index > 0 else None
        else:
            active_id = self._collection.active_id
        self._commit(items, active_id, persist)

    def activate(self, id_or_name: str | None, *, persist: bool = True) -> None:
        active_id = self.get(id_or_name).id if id_or_name is not None else None
        if active_id == self._collection.active_id:
            return
        self._commit(self._collection.items, active_id, persist)

    def _move(self, id_or_name: str, index: int, *, persist: bool = True) -> None:
        source = self.get(id_or_name)
        if not 0 <= index < len(self._collection.items):
            raise VisualizationConfigError("index is outside the collection", path="index")
        remaining = [item for item in self._collection.items if item.id != source.id]
        remaining.insert(index, source)
        self._commit(tuple(remaining), self._collection.active_id, persist)

    def export_json(self) -> str:
        return self._collection.to_json()

    def import_json(
        self,
        value: str,
        *,
        replace: bool = False,
        persist: bool = True,
    ) -> tuple[VisualizationSpec, ...]:
        incoming = VisualizationCollection.from_json(value)
        if replace:
            self._commit(incoming.items, incoming.active_id, persist)
            return incoming.items
        if len(self._collection.items) + len(incoming.items) > MAX_ITEMS:
            raise VisualizationConfigError(
                f"at most {MAX_ITEMS} visualizations are allowed", path="items"
            )
        combined = self._collection.items
        imported: list[VisualizationSpec] = []
        for item in incoming.items:
            copied = clone_spec(
                item,
                id=str(uuid.uuid4()),
                name=self._unique_name(item.name, combined + tuple(imported)),
            )
            imported.append(copied)
        items = combined + tuple(imported)
        active_id = imported[-1].id if imported else self._collection.active_id
        self._commit(items, active_id, persist)
        return tuple(imported)

    def metadata(self) -> dict[str, Any]:
        return {"sql_notebook_kit": {"visualizations": json.loads(self.export_json())}}

    @property
    def theme(self) -> Any:
        from sql_notebook_kit.visualize.theme import ThemeContext

        return getattr(self._bridge, "theme", ThemeContext.fallback("light"))

    def subscribe_theme(self, listener: Any) -> None:
        subscribe = getattr(self._bridge, "subscribe_theme", None)
        if subscribe is not None:
            subscribe(listener)


__all__ = ["PersistenceBridge", "SessionPersistenceBridge", "VisualizationManager"]
