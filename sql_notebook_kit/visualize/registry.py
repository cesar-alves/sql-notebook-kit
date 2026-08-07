"""Declarative visualization registry used by validation and editors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sql_notebook_kit.errors import VisualizationConfigError
from sql_notebook_kit.visualize.models import ChartType, JSONValue, VisualizationSpec

ColumnKind = Literal["numeric", "datetime", "categorical", "boolean", "unsupported"]


@dataclass(frozen=True, slots=True)
class FieldRoleDefinition:
    role: str
    label: str
    minimum: int
    maximum: int
    dtypes: tuple[ColumnKind, ...]
    aggregations: tuple[str, ...] = ("none",)
    date_grains: tuple[str, ...] = ("none",)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "role": self.role,
            "label": self.label,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "dtypes": list(self.dtypes),
            "aggregations": list(self.aggregations),
            "date_grains": list(self.date_grains),
        }


@dataclass(frozen=True, slots=True)
class ControlDefinition:
    key: str
    label: str
    section: Literal["general", "axes", "series", "style", "labels", "filters"]
    kind: str
    default: JSONValue
    choices: tuple[JSONValue, ...] = ()
    help_text: str = ""
    target: Literal["transform", "express", "trace", "layout", "renderer"] = "renderer"

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "key": self.key,
            "label": self.label,
            "section": self.section,
            "kind": self.kind,
            "default": self.default,
            "choices": list(self.choices),
            "help_text": self.help_text,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class VisualizationDefinition:
    id: ChartType
    label: str
    description: str
    inference_priority: int
    fields: tuple[FieldRoleDefinition, ...]
    controls: tuple[ControlDefinition, ...] = ()

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "inference_priority": self.inference_priority,
            "fields": [item.to_dict() for item in self.fields],
            "controls": [item.to_dict() for item in self.controls],
        }


ALL: tuple[ColumnKind, ...] = ("numeric", "datetime", "categorical", "boolean")
DIMENSION: tuple[ColumnKind, ...] = ("datetime", "categorical", "boolean", "numeric")
MEASURE_AGGS = (
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
)
CAT_AGGS = ("none", "count", "count_distinct")
DATE_GRAINS = ("none", "year", "quarter", "month", "week", "day", "hour", "minute")


def role(
    name: str,
    label: str,
    minimum: int,
    maximum: int,
    dtypes: tuple[ColumnKind, ...],
    aggregations: tuple[str, ...] = ("none",),
    date_grains: tuple[str, ...] = ("none",),
) -> FieldRoleDefinition:
    return FieldRoleDefinition(name, label, minimum, maximum, dtypes, aggregations, date_grains)


def control(
    key: str,
    label: str,
    section: Literal["general", "axes", "series", "style", "labels", "filters"],
    kind: str,
    default: JSONValue,
    *choices: JSONValue,
    target: str = "renderer",
) -> ControlDefinition:
    return ControlDefinition(key, label, section, kind, default, choices, target=target)  # type: ignore[arg-type]


COMMON_CONTROLS = (
    control("title", "Title", "style", "text", None, target="layout"),
    control(
        "palette", "Palette", "style", "select", "auto", "auto", "plotly", "d3", "safe", "vivid"
    ),
    control(
        "legend_position",
        "Legend",
        "style",
        "select",
        "right",
        "right",
        "left",
        "top",
        "bottom",
        "hidden",
        target="layout",
    ),
    control(
        "legend_order",
        "Legend order",
        "style",
        "select",
        "normal",
        "normal",
        "reversed",
        target="layout",
    ),
    control(
        "missing_value_policy",
        "Missing values",
        "style",
        "select",
        "hide",
        "hide",
        "zero",
        target="transform",
    ),
    control("show_data_labels", "Show labels", "labels", "checkbox", False, target="trace"),
    control("number_format", "Number format", "labels", "text", None, target="trace"),
    control("date_format", "Date format", "labels", "text", None, target="trace"),
    control("sort_by", "Sort field", "axes", "text", None, target="transform"),
    control(
        "sort_direction",
        "Sort direction",
        "axes",
        "select",
        "ascending",
        "ascending",
        "descending",
        target="transform",
    ),
    control("limit", "Point limit", "axes", "integer", None, target="transform"),
)

AXIS_CONTROLS = (
    control(
        "x_scale",
        "X scale",
        "axes",
        "select",
        "auto",
        "auto",
        "linear",
        "log",
        "date",
        "category",
        target="layout",
    ),
    control(
        "y_scale",
        "Y scale",
        "axes",
        "select",
        "auto",
        "auto",
        "linear",
        "log",
        target="layout",
    ),
    control("x_label", "X label", "axes", "text", None, target="layout"),
    control("y_label", "Y label", "axes", "text", None, target="layout"),
    control("show_x_axis", "Show X axis", "axes", "checkbox", True, target="layout"),
    control("show_y_axis", "Show Y axis", "axes", "checkbox", True, target="layout"),
)


DEFINITIONS: tuple[VisualizationDefinition, ...] = (
    VisualizationDefinition(
        "table",
        "Table",
        "Display selected columns as a table.",
        50,
        (role("visible", "Visible columns", 0, 50, ALL),),
        COMMON_CONTROLS,
    ),
    VisualizationDefinition(
        "bar",
        "Bar",
        "Compare measures across a dimension.",
        20,
        (
            role("x", "X", 1, 1, DIMENSION, date_grains=DATE_GRAINS),
            role("y", "Y", 1, 50, ALL, MEASURE_AGGS),
            role("group", "Group", 0, 1, DIMENSION),
            role("error", "Symmetric error", 0, 1, ("numeric",)),
            role("error_lower", "Lower error", 0, 1, ("numeric",)),
            role("error_upper", "Upper error", 0, 1, ("numeric",)),
        ),
        COMMON_CONTROLS
        + AXIS_CONTROLS
        + (
            control(
                "orientation", "Orientation", "axes", "select", "vertical", "vertical", "horizontal"
            ),
            control("bar_mode", "Bar mode", "series", "select", "grouped", "grouped", "stacked"),
            control("normalize", "Normalize", "series", "checkbox", False),
        ),
    ),
    VisualizationDefinition(
        "line",
        "Line",
        "Show change across an ordered dimension.",
        10,
        (
            role("x", "X", 1, 1, DIMENSION, date_grains=DATE_GRAINS),
            role("y", "Y", 1, 50, ALL, MEASURE_AGGS),
            role("group", "Group", 0, 1, DIMENSION),
            role("error", "Symmetric error", 0, 1, ("numeric",)),
            role("error_lower", "Lower error", 0, 1, ("numeric",)),
            role("error_upper", "Upper error", 0, 1, ("numeric",)),
        ),
        COMMON_CONTROLS
        + AXIS_CONTROLS
        + (
            control("show_lines", "Lines", "series", "checkbox", True),
            control("show_markers", "Markers", "series", "checkbox", False),
        ),
    ),
    VisualizationDefinition(
        "area",
        "Area",
        "Show filled series across a dimension.",
        30,
        (
            role("x", "X", 1, 1, DIMENSION, date_grains=DATE_GRAINS),
            role("y", "Y", 1, 50, ALL, MEASURE_AGGS),
            role("group", "Group", 0, 1, DIMENSION),
        ),
        COMMON_CONTROLS
        + AXIS_CONTROLS
        + (
            control("area_mode", "Area mode", "series", "select", "stacked", "stacked", "overlay"),
            control("normalize", "Normalize", "series", "checkbox", False),
        ),
    ),
    VisualizationDefinition(
        "scatter",
        "Scatter",
        "Compare two numeric measures.",
        30,
        (
            role("x", "X", 1, 1, ("numeric",)),
            role("y", "Y", 1, 1, ("numeric",)),
            role("group", "Group", 0, 1, DIMENSION),
            role("error", "Symmetric error", 0, 1, ("numeric",)),
            role("error_lower", "Lower error", 0, 1, ("numeric",)),
            role("error_upper", "Upper error", 0, 1, ("numeric",)),
        ),
        COMMON_CONTROLS
        + AXIS_CONTROLS
        + (control("marker_opacity", "Marker opacity", "series", "number", 0.8),),
    ),
    VisualizationDefinition(
        "bubble",
        "Bubble",
        "Encode a third numeric measure as marker size.",
        40,
        (
            role("x", "X", 1, 1, ("numeric",)),
            role("y", "Y", 1, 1, ("numeric",)),
            role("size", "Size", 1, 1, ("numeric",)),
            role("group", "Group", 0, 1, DIMENSION),
        ),
        COMMON_CONTROLS
        + AXIS_CONTROLS
        + (
            control("size_coefficient", "Size coefficient", "series", "number", 1.0),
            control("size_mode", "Size mode", "series", "select", "area", "area", "diameter"),
        ),
    ),
    VisualizationDefinition(
        "box",
        "Box",
        "Display distributions and quartiles.",
        40,
        (
            role("value", "Value", 1, 1, ("numeric",)),
            role("category", "Category", 0, 1, DIMENSION),
            role("group", "Group", 0, 1, DIMENSION),
        ),
        COMMON_CONTROLS
        + AXIS_CONTROLS
        + (
            control(
                "orientation", "Orientation", "axes", "select", "vertical", "vertical", "horizontal"
            ),
            control(
                "show_points", "Points", "series", "select", "outliers", "none", "outliers", "all"
            ),
        ),
    ),
    VisualizationDefinition(
        "pie",
        "Pie",
        "Show parts of a whole.",
        40,
        (
            role("category", "Category", 1, 1, DIMENSION),
            role("value", "Value", 1, 1, ("numeric",), MEASURE_AGGS),
        ),
        COMMON_CONTROLS
        + (
            control("hole", "Hole size", "style", "number", 0.0),
            control(
                "label_content",
                "Label content",
                "labels",
                "select",
                "label",
                "label",
                "value",
                "percent",
                "label_percent",
            ),
        ),
    ),
    VisualizationDefinition(
        "histogram",
        "Histogram",
        "Display numeric or datetime frequency.",
        40,
        (
            role("value", "Value", 1, 1, ("numeric", "datetime")),
            role("group", "Group", 0, 1, DIMENSION),
        ),
        COMMON_CONTROLS
        + AXIS_CONTROLS
        + (
            control("bin_count", "Bins", "axes", "integer", 20),
            control("histogram_mode", "Mode", "series", "select", "overlay", "overlay", "stack"),
        ),
    ),
    VisualizationDefinition(
        "heatmap",
        "Heatmap",
        "Encode a numeric measure by color.",
        40,
        (
            role("x", "X", 1, 1, DIMENSION),
            role("y", "Y", 1, 1, DIMENSION),
            role("color", "Color", 1, 1, ("numeric",), MEASURE_AGGS),
        ),
        COMMON_CONTROLS
        + (
            control("colorscale", "Colorscale", "style", "text", "Viridis"),
            control("reverse_scale", "Reverse scale", "style", "checkbox", False),
        ),
    ),
    VisualizationDefinition(
        "combo",
        "Combo",
        "Combine query-prepared bar and line series.",
        40,
        (
            role("x", "X", 1, 1, DIMENSION, date_grains=DATE_GRAINS),
            role("y", "Y", 2, 50, ("numeric",)),
        ),
        COMMON_CONTROLS + AXIS_CONTROLS,
    ),
    VisualizationDefinition(
        "counter",
        "Counter",
        "Display one value and optional target.",
        40,
        (
            role("value", "Value", 1, 1, ("numeric",)),
            role("target", "Target", 0, 1, ("numeric",)),
        ),
        COMMON_CONTROLS
        + (
            control("value_row", "Value row", "general", "integer", 0),
            control("target_row", "Target row", "general", "integer", 0),
            control(
                "comparison",
                "Comparison",
                "labels",
                "select",
                "absolute",
                "absolute",
                "relative",
                "percent",
            ),
        ),
    ),
)

_BY_ID = {item.id: item for item in DEFINITIONS}


def list_visualization_definitions() -> tuple[VisualizationDefinition, ...]:
    return DEFINITIONS


def get_visualization_definition(chart_type: ChartType) -> VisualizationDefinition:
    try:
        return _BY_ID[chart_type]
    except KeyError as exc:
        raise VisualizationConfigError("unsupported chart type", path="chart_type") from exc


def default_options(chart_type: ChartType) -> dict[str, JSONValue]:
    return {item.key: item.default for item in get_visualization_definition(chart_type).controls}


def validate_option_keys(spec: VisualizationSpec) -> None:
    controls = {item.key: item for item in get_visualization_definition(spec.chart_type).controls}
    unknown = set(spec.options) - set(controls)
    if unknown:
        raise VisualizationConfigError(f"unknown option {sorted(unknown)[0]!r}", path="options")
    for key, value in spec.options.items():
        item = controls[key]
        if item.choices and value not in item.choices:
            raise VisualizationConfigError("unsupported choice", path=f"options.{key}")
        if (
            item.kind == "integer"
            and value is not None
            and (isinstance(value, bool) or not isinstance(value, int))
        ):
            raise VisualizationConfigError("must be an integer", path=f"options.{key}")
        if item.kind == "number" and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise VisualizationConfigError("must be numeric", path=f"options.{key}")
        if item.kind == "checkbox" and not isinstance(value, bool):
            raise VisualizationConfigError("must be a boolean", path=f"options.{key}")
        if item.kind == "text" and value is not None and not isinstance(value, str):
            raise VisualizationConfigError("must be text or null", path=f"options.{key}")


__all__ = [
    "ControlDefinition",
    "FieldRoleDefinition",
    "VisualizationDefinition",
    "get_visualization_definition",
    "list_visualization_definitions",
]
