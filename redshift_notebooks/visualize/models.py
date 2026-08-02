"""Public, data-independent visualization specifications."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field, fields
from typing import Any, Literal, TypeAlias, TypeVar, cast

from redshift_notebooks.errors import VisualizationConfigError

ChartType = Literal[
    "table",
    "bar",
    "line",
    "area",
    "scatter",
    "bubble",
    "box",
    "pie",
    "histogram",
    "heatmap",
    "combo",
    "counter",
]
Aggregation = Literal[
    "none",
    "sum",
    "average",
    "count",
    "count_distinct",
    "min",
    "max",
    "median",
    "standard_deviation",
    "variance",
]
DateGrain = Literal["none", "year", "quarter", "month", "week", "day", "hour", "minute"]
JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

MAX_COLLECTION_BYTES = 256 * 1024
MAX_ITEMS = 50
MAX_FILTERS = 50
MAX_FIELDS = 50
MAX_JSON_DEPTH = 20
AGGREGATIONS = {
    "none",
    "sum",
    "average",
    "count",
    "count_distinct",
    "min",
    "max",
    "median",
    "standard_deviation",
    "variance",
}
DATE_GRAINS = {"none", "year", "quarter", "month", "week", "day", "hour", "minute"}
CHART_TYPES = {
    "table",
    "bar",
    "line",
    "area",
    "scatter",
    "bubble",
    "box",
    "pie",
    "histogram",
    "heatmap",
    "combo",
    "counter",
}


def _fail(message: str, path: str) -> None:
    raise VisualizationConfigError(message, path=path)


def validate_json_value(value: Any, *, path: str = "value", depth: int = 0) -> JSONValue:
    """Validate and detach a recursively JSON-compatible value."""
    if depth > MAX_JSON_DEPTH:
        _fail(f"nesting exceeds {MAX_JSON_DEPTH}", path)
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("must be finite", path)
        return value
    if isinstance(value, (list, tuple)):
        return [
            validate_json_value(item, path=f"{path}[{index}]", depth=depth + 1)
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("mapping keys must be strings", path)
            result[key] = validate_json_value(item, path=f"{path}.{key}", depth=depth + 1)
        return result
    _fail(f"unsupported JSON value type {type(value).__name__}", path)
    raise AssertionError("unreachable")


def _strict_keys(cls: type[Any], value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("must be an object", path)
    allowed = {item.name for item in fields(cls)}
    unknown = set(value) - allowed
    if unknown:
        _fail(f"unknown key {sorted(unknown)[0]!r}", path)
    return cast(dict[str, Any], value)


def _uuid4(value: str, path: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise VisualizationConfigError("must be a UUID", path=path) from exc
    if parsed.version != 4 or str(parsed) != value or value.lower() != value:
        _fail("must be a lowercase UUIDv4", path)
    return value


def _name(value: str, path: str = "name") -> str:
    if not isinstance(value, str):
        _fail("must be a string", path)
    normalized = value.strip()
    if not normalized:
        _fail("must contain a visible character", path)
    if len(normalized) > 80:
        _fail("must not exceed 80 Unicode code points", path)
    return normalized


@dataclass(frozen=True, slots=True)
class FieldBinding:
    role: str
    column: str
    column_index: int
    aggregation: Aggregation = "none"
    date_grain: DateGrain = "none"
    label: str | None = None
    axis: Literal["left", "right"] = "left"
    trace_type: Literal["bar", "line"] | None = None

    def __post_init__(self) -> None:
        if not self.role:
            _fail("must not be empty", "fields.role")
        if self.column_index < 0:
            _fail("must be non-negative", "fields.column_index")
        if self.aggregation not in AGGREGATIONS:
            _fail("unsupported aggregation", "fields.aggregation")
        if self.date_grain not in DATE_GRAINS:
            _fail("unsupported date grain", "fields.date_grain")

    def to_dict(self) -> dict[str, JSONValue]:
        return {item.name: cast(JSONValue, getattr(self, item.name)) for item in fields(self)}

    @classmethod
    def from_dict(cls, value: Any) -> FieldBinding:
        return cls(**_strict_keys(cls, value, "field"))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> FieldBinding:
        return cls.from_dict(json.loads(value))


@dataclass(frozen=True, slots=True)
class FilterSpec:
    column: str
    column_index: int
    operator: str
    value: JSONValue = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.column_index < 0:
            _fail("must be non-negative", "filters.column_index")
        if not self.operator:
            _fail("must not be empty", "filters.operator")
        object.__setattr__(self, "value", validate_json_value(self.value, path="filters.value"))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "column": self.column,
            "column_index": self.column_index,
            "operator": self.operator,
            "value": self.value,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, value: Any) -> FilterSpec:
        return cls(**_strict_keys(cls, value, "filter"))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> FilterSpec:
        return cls.from_dict(json.loads(value))


@dataclass(frozen=True, slots=True)
class PlotlyOverrides:
    trace: dict[str, JSONValue] = field(default_factory=dict)
    layout: dict[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "trace", validate_json_value(self.trace, path="plotly_overrides.trace")
        )
        object.__setattr__(
            self, "layout", validate_json_value(self.layout, path="plotly_overrides.layout")
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {"trace": self.trace, "layout": self.layout}

    @classmethod
    def from_dict(cls, value: Any) -> PlotlyOverrides:
        return cls(**_strict_keys(cls, value, "plotly_overrides"))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> PlotlyOverrides:
        return cls.from_dict(json.loads(value))


@dataclass(frozen=True, slots=True)
class VisualizationSpec:
    schema_version: Literal[1]
    id: str
    name: str
    chart_type: ChartType
    fields: tuple[FieldBinding, ...] = ()
    filters: tuple[FilterSpec, ...] = ()
    options: dict[str, JSONValue] = field(default_factory=dict)
    plotly_overrides: PlotlyOverrides | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            _fail("unsupported schema version", "schema_version")
        _uuid4(self.id, "id")
        object.__setattr__(self, "name", _name(self.name))
        if self.chart_type not in CHART_TYPES:
            _fail("unsupported chart type", "chart_type")
        if len(self.fields) > MAX_FIELDS:
            _fail(f"must contain at most {MAX_FIELDS} bindings", "fields")
        if len(self.filters) > MAX_FILTERS:
            _fail(f"must contain at most {MAX_FILTERS} filters", "filters")
        object.__setattr__(self, "options", validate_json_value(self.options, path="options"))

    @classmethod
    def create(cls, name: str, chart_type: ChartType, **kwargs: Any) -> VisualizationSpec:
        return cls(1, str(uuid.uuid4()), name, chart_type, **kwargs)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "chart_type": self.chart_type,
            "fields": [item.to_dict() for item in self.fields],
            "filters": [item.to_dict() for item in self.filters],
            "options": self.options,
            "plotly_overrides": self.plotly_overrides.to_dict() if self.plotly_overrides else None,
        }

    @classmethod
    def from_dict(cls, value: Any) -> VisualizationSpec:
        data = _strict_keys(cls, value, "visualization")
        data["fields"] = tuple(FieldBinding.from_dict(item) for item in data.get("fields", ()))
        data["filters"] = tuple(FilterSpec.from_dict(item) for item in data.get("filters", ()))
        override = data.get("plotly_overrides")
        data["plotly_overrides"] = (
            PlotlyOverrides.from_dict(override) if override is not None else None
        )
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> VisualizationSpec:
        return cls.from_dict(json.loads(value))


@dataclass(frozen=True, slots=True)
class VisualizationCollection:
    schema_version: Literal[1] = 1
    revision: int = 0
    active_id: str | None = None
    items: tuple[VisualizationSpec, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            _fail("unsupported schema version", "schema_version")
        if self.revision < 0:
            _fail("must be non-negative", "revision")
        if len(self.items) > MAX_ITEMS:
            _fail(f"must contain at most {MAX_ITEMS} items", "items")
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            _fail("IDs must be unique", "items")
        if self.active_id is not None and self.active_id not in ids:
            _fail("must identify an item in the collection", "active_id")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "active_id": self.active_id,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, value: Any) -> VisualizationCollection:
        data = _strict_keys(cls, value, "collection")
        data["items"] = tuple(VisualizationSpec.from_dict(item) for item in data.get("items", ()))
        result = cls(**data)
        if len(result.to_json().encode()) > MAX_COLLECTION_BYTES:
            _fail(f"serialized collection exceeds {MAX_COLLECTION_BYTES} bytes", "collection")
        return result

    def to_json(self) -> str:
        value = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        if len(value.encode()) > MAX_COLLECTION_BYTES:
            _fail(f"serialized collection exceeds {MAX_COLLECTION_BYTES} bytes", "collection")
        return value

    @classmethod
    def from_json(cls, value: str) -> VisualizationCollection:
        if len(value.encode()) > MAX_COLLECTION_BYTES:
            _fail(f"serialized collection exceeds {MAX_COLLECTION_BYTES} bytes", "collection")
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise VisualizationConfigError("invalid JSON", path="collection") from exc
        return cls.from_dict(decoded)


SpecT = TypeVar(
    "SpecT", FieldBinding, FilterSpec, PlotlyOverrides, VisualizationSpec, VisualizationCollection
)


def clone_spec(spec: VisualizationSpec, **changes: Any) -> VisualizationSpec:
    """Create a deep, revalidated copy with selected changes."""
    data = spec.to_dict()
    data.update(changes)
    return VisualizationSpec.from_dict(data)


__all__ = [
    "Aggregation",
    "ChartType",
    "FieldBinding",
    "FilterSpec",
    "JSONValue",
    "PlotlyOverrides",
    "VisualizationCollection",
    "VisualizationSpec",
]
