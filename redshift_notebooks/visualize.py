"""Optional, bounded Plotly visualization for notebook query results."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import pandas as pd

ChartType = Literal["table", "bar", "line", "area", "scatter", "pie", "histogram", "value"]
Aggregation = Literal["none", "sum", "average", "count", "count_distinct", "min", "max", "median"]


@dataclass(frozen=True, slots=True)
class FilterSpec:
    """A serializable local-data filter."""

    column: str
    operator: Literal["eq", "ne", "gt", "ge", "lt", "le", "contains", "in"]
    value: Any


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """Serializable chart configuration independent of notebook widgets."""

    chart_type: ChartType = "table"
    x: str | None = None
    y: tuple[str, ...] = ()
    color: str | None = None
    aggregation: Aggregation = "none"
    filters: tuple[FilterSpec, ...] = ()
    sort_by: str | None = None
    sort_descending: bool = False
    limit: int | None = None
    title: str | None = None
    x_label: str | None = None
    y_label: str | None = None

    @classmethod
    def infer(cls, frame: pd.DataFrame) -> ChartSpec:
        """Choose conservative defaults from pandas column types."""
        if frame.empty or not len(frame.columns):
            return cls()
        numeric = list(frame.select_dtypes(include="number").columns)
        datetime = list(frame.select_dtypes(include=["datetime", "datetimetz"]).columns)
        categorical = [column for column in frame.columns if column not in numeric + datetime]
        if datetime and numeric:
            return cls(chart_type="line", x=str(datetime[0]), y=(str(numeric[0]),))
        if categorical and numeric:
            return cls(chart_type="bar", x=str(categorical[0]), y=(str(numeric[0]),))
        if len(numeric) >= 2:
            return cls(chart_type="scatter", x=str(numeric[0]), y=(str(numeric[1]),))
        if numeric:
            return cls(chart_type="histogram", x=str(numeric[0]))
        return cls(chart_type="table")

    def to_json(self) -> str:
        """Serialize the chart definition without any result data."""
        return json.dumps(asdict(self), sort_keys=True, default=str)

    @classmethod
    def from_json(cls, value: str) -> ChartSpec:
        """Restore a chart definition produced by :meth:`to_json`."""
        data = json.loads(value)
        data["y"] = tuple(data.get("y", ()))
        data["filters"] = tuple(FilterSpec(**item) for item in data.get("filters", ()))
        return cls(**data)

    def to_code(self, result_name: str = "result") -> str:
        """Generate reproducible Python for a notebook cell."""
        return f"{result_name}.visualize(ChartSpec.from_json({self.to_json()!r}))"


def _apply_filter(frame: pd.DataFrame, item: FilterSpec) -> pd.DataFrame:
    series = frame[item.column]
    operations = {
        "eq": lambda: series == item.value,
        "ne": lambda: series != item.value,
        "gt": lambda: series > item.value,
        "ge": lambda: series >= item.value,
        "lt": lambda: series < item.value,
        "le": lambda: series <= item.value,
        "contains": lambda: series.astype("string").str.contains(str(item.value), na=False),
        "in": lambda: series.isin(item.value),
    }
    return frame[operations[item.operator]()].copy()


def prepare_data(frame: pd.DataFrame, spec: ChartSpec) -> pd.DataFrame:
    """Apply deterministic local filters, aggregation, sorting, and limits."""
    result = frame.copy()
    for item in spec.filters:
        if item.column not in result.columns:
            raise ValueError(f"filter column {item.column!r} does not exist")
        result = _apply_filter(result, item)

    groups = [column for column in (spec.x, spec.color) if column]
    if spec.aggregation != "none" and groups:
        if spec.aggregation == "count":
            result = result.groupby(groups, dropna=False).size().reset_index(name="count")
        elif spec.aggregation == "count_distinct":
            if not spec.y:
                raise ValueError("count_distinct requires a y column")
            result = result.groupby(groups, dropna=False)[list(spec.y)].nunique().reset_index()
        else:
            if not spec.y:
                raise ValueError(f"{spec.aggregation} requires a y column")
            operation = "mean" if spec.aggregation == "average" else spec.aggregation
            result = result.groupby(groups, dropna=False)[list(spec.y)].agg(operation).reset_index()
    if spec.sort_by:
        if spec.sort_by not in result.columns:
            raise ValueError(f"sort column {spec.sort_by!r} does not exist")
        result = result.sort_values(spec.sort_by, ascending=not spec.sort_descending)
    if spec.limit is not None:
        if spec.limit < 1:
            raise ValueError("limit must be positive")
        result = result.head(spec.limit)
    return result


def build_figure(frame: pd.DataFrame, spec: ChartSpec) -> Any:
    """Create a Plotly figure from prepared local data."""
    import plotly.express as px
    import plotly.graph_objects as go

    data = prepare_data(frame, spec)
    labels: dict[str, str] = {}
    if spec.y_label:
        labels.update({column: spec.y_label for column in spec.y})
    if spec.x and spec.x_label:
        labels[spec.x] = spec.x_label
    common = {"title": spec.title, "labels": labels}
    y: str | list[str] | None = list(spec.y) or None
    if spec.chart_type == "table":
        table = go.Table(
            header={"values": list(data.columns)},
            cells={"values": [data[column] for column in data.columns]},
        )
        return go.Figure(data=[table])
    if spec.chart_type == "bar":
        return px.bar(data, x=spec.x, y=y, color=spec.color, **common)
    if spec.chart_type == "line":
        return px.line(data, x=spec.x, y=y, color=spec.color, **common)
    if spec.chart_type == "area":
        return px.area(data, x=spec.x, y=y, color=spec.color, **common)
    if spec.chart_type == "scatter":
        y_column = spec.y[0] if spec.y else None
        return px.scatter(data, x=spec.x, y=y_column, color=spec.color, **common)
    if spec.chart_type == "pie":
        value_column = spec.y[0] if spec.y else None
        return px.pie(data, names=spec.x, values=value_column, color=spec.color, **common)
    if spec.chart_type == "histogram":
        return px.histogram(data, x=spec.x, color=spec.color, **common)
    if spec.chart_type == "value":
        value = data[spec.y[0]].iloc[0] if spec.y and not data.empty else None
        indicator_title = spec.title or (spec.y[0] if spec.y else "Value")
        indicator = go.Indicator(
            mode="number",
            value=0 if value is None else value,
            title={"text": indicator_title},
        )
        return go.Figure(indicator)
    raise ValueError(f"unsupported chart type: {spec.chart_type}")


def build_chart_builder(result: Any, initial_spec: ChartSpec) -> Any:
    """Build Table/Visualization tabs and interactive chart controls."""
    import ipywidgets as widgets
    from IPython.display import clear_output, display

    columns = [str(column) for column in result.dataframe.columns]
    optional_columns = [("—", None), *[(column, column) for column in columns]]
    chart_type = widgets.Dropdown(
        description="Chart",
        options=["table", "bar", "line", "area", "scatter", "pie", "histogram", "value"],
        value=initial_spec.chart_type,
    )
    x = widgets.Dropdown(description="X", options=optional_columns, value=initial_spec.x)
    y = widgets.SelectMultiple(description="Y", options=columns, value=initial_spec.y)
    color = widgets.Dropdown(
        description="Group",
        options=optional_columns,
        value=initial_spec.color,
    )
    aggregation = widgets.Dropdown(
        description="Aggregate",
        options=["none", "sum", "average", "count", "count_distinct", "min", "max", "median"],
        value=initial_spec.aggregation,
    )
    title = widgets.Text(description="Title", value=initial_spec.title or "")
    initial_filter = initial_spec.filters[0] if initial_spec.filters else None
    filter_column = widgets.Dropdown(
        description="Filter",
        options=optional_columns,
        value=initial_filter.column if initial_filter else None,
    )
    filter_operator = widgets.Dropdown(
        description="Operator",
        options=["eq", "ne", "gt", "ge", "lt", "le", "contains"],
        value=initial_filter.operator if initial_filter else "eq",
    )
    filter_value = widgets.Text(
        description="Value",
        value=str(initial_filter.value) if initial_filter else "",
    )
    sort_by = widgets.Dropdown(
        description="Sort",
        options=optional_columns,
        value=initial_spec.sort_by,
    )
    descending = widgets.Checkbox(
        description="Descending",
        value=initial_spec.sort_descending,
    )
    limit = widgets.BoundedIntText(
        description="Point limit",
        value=initial_spec.limit or 0,
        min=0,
        max=result.max_rows,
    )
    chart_output = widgets.Output()
    table_output = widgets.Output()
    notice = widgets.HTML(
        value=(
            f"<b>Bounded result:</b> using the first {result.max_rows:,} rows; "
            "unfetched rows are excluded."
            if result.truncated
            else f"Using {len(result.dataframe):,} local rows."
        )
    )

    with table_output:
        display(result.dataframe)

    def render(_change: Any = None) -> None:
        filters: tuple[FilterSpec, ...] = ()
        if filter_column.value is not None and filter_value.value:
            try:
                parsed_filter_value = json.loads(filter_value.value)
            except json.JSONDecodeError:
                parsed_filter_value = filter_value.value
            filters = (
                FilterSpec(
                    column=filter_column.value,
                    operator=filter_operator.value,
                    value=parsed_filter_value,
                ),
            )
        spec = ChartSpec(
            chart_type=chart_type.value,
            x=x.value,
            y=tuple(y.value),
            color=color.value,
            aggregation=aggregation.value,
            filters=filters,
            sort_by=sort_by.value,
            sort_descending=descending.value,
            limit=limit.value or None,
            title=title.value or None,
        )
        with chart_output:
            clear_output(wait=True)
            try:
                figure = build_figure(result.dataframe, spec)
                result.chart = figure
                display(figure)
            except Exception as exc:
                display(widgets.HTML(value=f"<b>Chart configuration error:</b> {exc}"))

    for control in (
        chart_type,
        x,
        y,
        color,
        aggregation,
        title,
        filter_column,
        filter_operator,
        filter_value,
        sort_by,
        descending,
        limit,
    ):
        control.observe(render, names="value")
    render()
    editor = widgets.VBox(
        [
            notice,
            widgets.HBox([chart_type, x, color]),
            widgets.HBox([y, aggregation]),
            widgets.HBox([filter_column, filter_operator, filter_value]),
            widgets.HBox([sort_by, descending, limit]),
            title,
            chart_output,
        ]
    )
    tabs = widgets.Tab(children=[table_output, editor])
    tabs.set_title(0, "Table")
    tabs.set_title(1, "Visualization")
    return tabs
