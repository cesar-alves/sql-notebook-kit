"""In-memory visualization collection management and persistence boundary."""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from typing import Any, Protocol

from redshift_notebooks.errors import VisualizationConfigError, VisualizationPersistenceError
from redshift_notebooks.visualize.models import (
    MAX_ITEMS,
    VisualizationCollection,
    VisualizationSpec,
    clone_spec,
)


class PersistenceBridge(Protocol):
    available: bool
    reason: str | None

    def load(self) -> VisualizationCollection: ...

    def save(self, collection: VisualizationCollection, *, expected_revision: int) -> int: ...


class SessionPersistenceBridge:
    """Explicit session-only fallback used when no frontend companion responds."""

    available = False

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
        if bridge is None:
            from redshift_notebooks.visualize.protocol import create_persistence_bridge

            bridge = create_persistence_bridge(getattr(result, "cell_id", None))
        self._bridge = bridge or SessionPersistenceBridge()
        if collection is None and self._bridge.available:
            try:
                collection = self._bridge.load()
            except VisualizationPersistenceError:
                collection = None
        self._collection = collection or VisualizationCollection()
        self.dirty = False
        self.persistence_error: str | None = self._bridge.reason

    @property
    def collection(self) -> VisualizationCollection:
        return self._collection

    @property
    def persistence_available(self) -> bool:
        return self._bridge.available

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
        try:
            revision = self._bridge.save(next_collection, expected_revision=previous_revision)
        except VisualizationPersistenceError as exc:
            self.dirty = True
            self.persistence_error = str(exc)
        else:
            self._collection = replace(next_collection, revision=revision)
            self.dirty = False
            self.persistence_error = None

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
        return {"redshift_notebooks": {"visualizations": json.loads(self.export_json())}}

    @property
    def theme(self) -> Any:
        from redshift_notebooks.visualize.theme import ThemeContext

        return getattr(self._bridge, "theme", ThemeContext.fallback("light"))

    def subscribe_theme(self, listener: Any) -> None:
        subscribe = getattr(self._bridge, "subscribe_theme", None)
        if subscribe is not None:
            subscribe(listener)


__all__ = ["PersistenceBridge", "SessionPersistenceBridge", "VisualizationManager"]
