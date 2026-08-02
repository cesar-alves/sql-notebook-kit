"""Column inference, deterministic local transforms, and Plotly renderers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from redshift_notebooks.errors import VisualizationConfigError, VisualizationRenderError
from redshift_notebooks.visualize.models import FieldBinding, FilterSpec, VisualizationSpec
from redshift_notebooks.visualize.registry import (
    ColumnKind,
    default_options,
    get_visualization_definition,
    validate_option_keys,
)
from redshift_notebooks.visualize.theme import ThemeContext, build_plotly_template


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    label: str
    index: int
    kind: ColumnKind


@dataclass(slots=True)
class PreparedData:
    """Detached prepared frame plus local row-count and binding metadata."""

    frame: Any
    source_rows: int
    filtered_rows: int
    plotted_rows: int
    columns: dict[int, str]

    def __getitem__(self, key: Any) -> Any:
        return self.frame[key]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.frame, name)


def classify_columns(frame: Any) -> tuple[ColumnInfo, ...]:
    from pandas.api import types as ptypes

    result: list[ColumnInfo] = []
    for index, label in enumerate(frame.columns):
        dtype = frame.dtypes.iloc[index]
        if ptypes.is_bool_dtype(dtype):
            kind: ColumnKind = "boolean"
        elif ptypes.is_numeric_dtype(dtype):
            kind = "numeric"
        elif ptypes.is_datetime64_any_dtype(dtype):
            kind = "datetime"
        elif (
            ptypes.is_string_dtype(dtype)
            or ptypes.is_categorical_dtype(dtype)
            or ptypes.is_object_dtype(dtype)
        ):
            kind = "categorical"
        else:
            kind = "unsupported"
        result.append(ColumnInfo(str(label), index, kind))
    return tuple(result)


def _binding(role: str, info: ColumnInfo) -> FieldBinding:
    return FieldBinding(role, info.label, info.index)


def infer_visualization(frame: Any, *, name: str = "Visualization 1") -> VisualizationSpec:
    columns = classify_columns(frame)
    numeric = [item for item in columns if item.kind == "numeric"]
    datetime = [item for item in columns if item.kind == "datetime"]
    categorical = [item for item in columns if item.kind in ("categorical", "boolean")]
    bindings: tuple[FieldBinding, ...]
    if datetime and numeric:
        chart_type = "line"
        bindings = (_binding("x", datetime[0]), _binding("y", numeric[0]))
    elif categorical and numeric:
        chart_type = "bar"
        bindings = (_binding("x", categorical[0]), _binding("y", numeric[0]))
    elif len(numeric) >= 2:
        chart_type = "scatter"
        bindings = (_binding("x", numeric[0]), _binding("y", numeric[1]))
    elif numeric:
        chart_type = "histogram"
        bindings = (_binding("value", numeric[0]),)
    else:
        chart_type = "table"
        bindings = ()
    return VisualizationSpec.create(
        name, cast(Any, chart_type), fields=bindings, options=default_options(cast(Any, chart_type))
    )


def _resolve(frame: Any, column: str, index: int, path: str) -> Any:
    if index >= len(frame.columns):
        raise VisualizationConfigError("column is missing", path=path)
    label = frame.columns[index]
    if str(label) != column:
        raise VisualizationConfigError("column moved or was replaced", path=path)
    return frame.iloc[:, index]


def validate_visualization(frame: Any, spec: VisualizationSpec) -> None:
    definition = get_visualization_definition(spec.chart_type)
    validate_option_keys(spec)
    info = {item.index: item for item in classify_columns(frame)}
    role_defs = {item.role: item for item in definition.fields}
    grouped: dict[str, list[FieldBinding]] = {}
    for index, filter_spec in enumerate(spec.filters):
        _resolve(
            frame,
            filter_spec.column,
            filter_spec.column_index,
            f"filters[{index}].column",
        )
        kind = info[filter_spec.column_index].kind
        common_operators = {"equals", "not_equals", "is_null", "is_not_null", "in", "not_in"}
        operators = set(common_operators)
        if kind in ("numeric", "datetime"):
            operators.update(
                {
                    "greater_than",
                    "greater_or_equal",
                    "less_than",
                    "less_or_equal",
                    "between",
                }
            )
        elif kind == "categorical":
            operators.update({"contains", "not_contains", "starts_with", "ends_with"})
        elif kind == "boolean":
            operators = {"equals", "not_equals", "is_null", "is_not_null"}
        if filter_spec.operator not in operators:
            raise VisualizationConfigError(
                "operator is not valid for this column type",
                path=f"filters[{index}].operator",
            )
    for index, binding in enumerate(spec.fields):
        grouped.setdefault(binding.role, []).append(binding)
        role_def = role_defs.get(binding.role)
        if role_def is None:
            raise VisualizationConfigError(
                "role is not supported for this chart", path=f"fields[{index}].role"
            )
        _resolve(frame, binding.column, binding.column_index, f"fields[{index}].column")
        column_info = info[binding.column_index]
        if column_info.kind not in role_def.dtypes:
            raise VisualizationConfigError(
                f"requires {', '.join(role_def.dtypes)} data", path=f"fields[{index}].column"
            )
        allowed_aggs = role_def.aggregations
        if binding.aggregation not in allowed_aggs:
            raise VisualizationConfigError(
                "aggregation is not allowed for this role", path=f"fields[{index}].aggregation"
            )
        if column_info.kind != "numeric" and binding.aggregation not in (
            "none",
            "count",
            "count_distinct",
        ):
            raise VisualizationConfigError(
                "aggregation requires numeric data", path=f"fields[{index}].aggregation"
            )
        if binding.date_grain not in role_def.date_grains:
            raise VisualizationConfigError(
                "date grain is not allowed for this role", path=f"fields[{index}].date_grain"
            )
        if binding.date_grain != "none" and column_info.kind != "datetime":
            raise VisualizationConfigError(
                "date grain requires datetime data", path=f"fields[{index}].date_grain"
            )
    for role_name, role_definition in role_defs.items():
        count = len(grouped.get(role_name, ()))
        if count < role_definition.minimum or count > role_definition.maximum:
            expected = (
                f"{role_definition.minimum}"
                if role_definition.minimum == role_definition.maximum
                else f"{role_definition.minimum} to {role_definition.maximum}"
            )
            raise VisualizationConfigError(
                f"requires {expected} binding(s)", path=f"fields.{role_name}"
            )
    if grouped.get("error") and (grouped.get("error_lower") or grouped.get("error_upper")):
        raise VisualizationConfigError(
            "symmetric and lower/upper errors cannot be combined", path="fields.error"
        )
    if bool(grouped.get("error_lower")) != bool(grouped.get("error_upper")):
        raise VisualizationConfigError(
            "lower and upper error bindings must be paired", path="fields.error_lower"
        )
    limit = spec.options.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise VisualizationConfigError("must be a positive integer", path="options.limit")
    bins = spec.options.get("bin_count")
    if bins is not None and (isinstance(bins, bool) or not isinstance(bins, int) or bins < 1):
        raise VisualizationConfigError("must be a positive integer", path="options.bin_count")
    for key in ("marker_opacity", "hole"):
        value = spec.options.get(key)
        if value is not None and not 0 <= cast(float, value) <= 1:
            raise VisualizationConfigError("must be between 0 and 1", path=f"options.{key}")
    coefficient = spec.options.get("size_coefficient")
    if coefficient is not None and cast(float, coefficient) <= 0:
        raise VisualizationConfigError("must be positive", path="options.size_coefficient")
    if spec.chart_type == "combo":
        for index, binding in enumerate(grouped["y"]):
            if binding.trace_type is None:
                raise VisualizationConfigError(
                    "combo measures require a trace type", path=f"fields.y[{index}].trace_type"
                )
            if binding.aggregation != "none":
                raise VisualizationConfigError(
                    "combo values must be query-prepared", path=f"fields.y[{index}].aggregation"
                )


def _literal_string_filter(series: Any, operator: str, value: Any) -> Any:
    if isinstance(value, dict):
        text = value.get("text")
        insensitive = value.get("case_insensitive", False)
        if not isinstance(text, str) or not isinstance(insensitive, bool):
            raise VisualizationConfigError(
                "requires text and a boolean case_insensitive flag", path="filters.value"
            )
    else:
        text, insensitive = value, False
    if not isinstance(text, str):
        raise VisualizationConfigError("requires a string", path="filters.value")
    values = series.astype("string")
    if insensitive:
        values, text = values.str.casefold(), text.casefold()
    operations = {
        "contains": lambda: values.str.contains(text, regex=False, na=False),
        "not_contains": lambda: ~values.str.contains(text, regex=False, na=False),
        "starts_with": lambda: values.str.startswith(text, na=False),
        "ends_with": lambda: values.str.endswith(text, na=False),
    }
    return operations[operator]()


def _coerce_filter_value(series: Any, value: Any) -> Any:
    import pandas as pd
    from pandas.api import types as ptypes

    if ptypes.is_datetime64_any_dtype(series.dtype):
        try:
            converted = pd.Timestamp(value)
            timezone = getattr(series.dt, "tz", None)
            if timezone is not None:
                if converted.tzinfo is None:
                    converted = converted.tz_localize(
                        timezone, ambiguous="raise", nonexistent="raise"
                    )
                else:
                    converted = converted.tz_convert(timezone)
            return converted
        except Exception as exc:
            raise VisualizationConfigError(
                "invalid or ambiguous datetime", path="filters.value"
            ) from exc
    if ptypes.is_numeric_dtype(series.dtype) and not isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise VisualizationConfigError(
                "requires a numeric value", path="filters.value"
            ) from exc
    return value


def _filter_mask(series: Any, item: FilterSpec) -> Any:
    operator = item.operator.replace(" ", "_")
    if operator == "is_null":
        return series.isna()
    if operator == "is_not_null":
        return series.notna()
    if operator in ("contains", "not_contains", "starts_with", "ends_with"):
        return _literal_string_filter(series, operator, item.value)
    if operator in ("in", "not_in"):
        if not isinstance(item.value, list) or not item.value:
            raise VisualizationConfigError("requires a non-empty array", path="filters.value")
        mask = series.isin([_coerce_filter_value(series, value) for value in item.value])
        return ~mask if operator == "not_in" else mask
    if operator == "between":
        if not isinstance(item.value, list) or len(item.value) != 2:
            raise VisualizationConfigError("requires a two-item array", path="filters.value")
        lower, upper = (_coerce_filter_value(series, value) for value in item.value)
        return series.between(lower, upper, inclusive="both")
    value = _coerce_filter_value(series, item.value)
    operations = {
        "equals": lambda: series == value,
        "eq": lambda: series == value,
        "not_equals": lambda: series != value,
        "ne": lambda: series != value,
        "greater_than": lambda: series > value,
        "gt": lambda: series > value,
        "greater_or_equal": lambda: series >= value,
        "ge": lambda: series >= value,
        "less_than": lambda: series < value,
        "lt": lambda: series < value,
        "less_or_equal": lambda: series <= value,
        "le": lambda: series <= value,
    }
    try:
        return operations[operator]()
    except KeyError as exc:
        raise VisualizationConfigError(
            "operator is not valid for this column", path="filters.operator"
        ) from exc


def _bucket(series: Any, grain: str) -> Any:
    if grain == "none":
        return series
    if grain in ("year", "quarter", "month", "week"):
        timezone = series.dt.tz
        values = series.dt.tz_localize(None) if timezone is not None else series
        bucketed = values.dt.to_period(
            {"year": "Y", "quarter": "Q", "month": "M", "week": "W"}[grain]
        ).dt.start_time
        return bucketed.dt.tz_localize(timezone) if timezone is not None else bucketed
    return series.dt.floor({"day": "D", "hour": "h", "minute": "min"}[grain])


def prepare_data(frame: Any, spec: VisualizationSpec) -> PreparedData:
    """Prepare a detached local frame in the specification's fixed operation order."""
    import pandas as pd

    validate_visualization(frame, spec)
    source_rows = len(frame)
    indices = sorted(
        {binding.column_index for binding in spec.fields}
        | {item.column_index for item in spec.filters}
    )
    if spec.chart_type == "table" and not spec.fields:
        indices = list(range(len(frame.columns)))
    internal = {index: f"__rn_column_{index}" for index in indices}
    data = frame.iloc[:, indices].copy(deep=True)
    data.columns = [internal[index] for index in indices]
    for filter_index, item in enumerate(spec.filters):
        if not item.enabled:
            continue
        key = internal[item.column_index]
        try:
            data = data.loc[_filter_mask(data[key], item).fillna(False)].copy()
        except VisualizationConfigError as exc:
            raise VisualizationConfigError(
                str(exc).split(": ", 1)[-1], path=f"filters[{filter_index}].value"
            ) from exc
    filtered_rows = len(data)
    for binding in spec.fields:
        if binding.date_grain != "none":
            key = internal[binding.column_index]
            data[key] = _bucket(data[key], binding.date_grain)

    bindings_by_role: dict[str, list[FieldBinding]] = {}
    for binding in spec.fields:
        bindings_by_role.setdefault(binding.role, []).append(binding)
    measures = [binding for binding in spec.fields if binding.role in ("y", "value", "color")]
    missing_measures = [binding for binding in measures if binding.aggregation != "count"]
    missing_policy = spec.options.get("missing_value_policy", "hide")
    if missing_policy == "zero":
        infos = {item.index: item for item in classify_columns(frame)}
        for binding in missing_measures:
            if infos[binding.column_index].kind != "numeric":
                raise VisualizationConfigError(
                    "zero is available only for numeric values", path="options.missing_value_policy"
                )
            data[internal[binding.column_index]] = data[internal[binding.column_index]].fillna(0)
    elif missing_policy == "hide" and missing_measures:
        data = data.dropna(subset=[internal[item.column_index] for item in missing_measures]).copy()

    aggregate_measures = [item for item in measures if item.aggregation != "none"]
    bypass = spec.chart_type in ("histogram", "box", "combo", "counter", "table")
    if aggregate_measures and not bypass:
        group_roles = ("x", "category", "group")
        groups = [item for item in spec.fields if item.role in group_roles]
        group_keys = [internal[item.column_index] for item in groups]
        parts: list[Any] = []
        for position, binding in enumerate(aggregate_measures):
            key = internal[binding.column_index]
            target = f"__rn_measure_{position}"
            grouped = data.groupby(group_keys, dropna=False, sort=False) if group_keys else None
            if binding.aggregation == "count":
                part = (
                    grouped.size().rename(target).reset_index()
                    if grouped is not None
                    else pd.DataFrame({target: [len(data)]})
                )
            else:
                operation = {
                    "average": "mean",
                    "count_distinct": "nunique",
                    "standard_deviation": "std",
                    "variance": "var",
                }.get(binding.aggregation, binding.aggregation)
                if grouped is not None:
                    part = grouped[key].agg(operation).rename(target).reset_index()
                else:
                    part = pd.DataFrame({target: [getattr(data[key], operation)()]})
            internal[binding.column_index] = target
            parts.append(part)
        data = parts[0]
        for part in parts[1:]:
            data = (
                data.merge(part, on=group_keys, how="outer", sort=False)
                if group_keys
                else pd.concat([data, part], axis=1)
            )

    sort_by = spec.options.get("sort_by")
    if sort_by:
        sort_key = None
        for binding in spec.fields:
            if sort_by in (binding.role, binding.column, str(binding.column_index)):
                sort_key = internal[binding.column_index]
                break
        if sort_key is None or sort_key not in data:
            raise VisualizationConfigError(
                "does not identify a rendered field", path="options.sort_by"
            )
        data = data.sort_values(
            sort_key, ascending=spec.options.get("sort_direction") != "descending", kind="stable"
        )
    limit = spec.options.get("limit")
    if limit is not None:
        data = data.head(cast(int, limit)).copy()

    if spec.chart_type == "heatmap" and not data.empty:
        x = internal[bindings_by_role["x"][0].column_index]
        y = internal[bindings_by_role["y"][0].column_index]
        color = internal[bindings_by_role["color"][0].column_index]
        data = data.pivot_table(index=y, columns=x, values=color, aggfunc="first", dropna=False)
    return PreparedData(data, source_rows, filtered_rows, len(data), internal)


def _field(
    spec: VisualizationSpec, prepared: PreparedData, role: str, position: int = 0
) -> str | None:
    bindings = [item for item in spec.fields if item.role == role]
    return prepared.columns[bindings[position].column_index] if len(bindings) > position else None


def _empty_figure(message: str, template: Any) -> Any:
    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_annotation(text=message, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper")
    figure.update_layout(template=template, xaxis={"visible": False}, yaxis={"visible": False})
    return figure


def build_figure(frame: Any, spec: VisualizationSpec, theme: ThemeContext | None = None) -> Any:
    """Validate, prepare, and render one visualization with an explicit theme."""
    import plotly.express as px
    import plotly.graph_objects as go

    theme = theme or ThemeContext.fallback("light")
    template = build_plotly_template(theme)
    prepared = prepare_data(frame, spec)
    data = prepared.frame
    options = {**default_options(spec.chart_type), **spec.options}
    title = cast(str | None, options.get("title"))
    if data.empty:
        return _empty_figure("No rows match this visualization.", template)
    x, y, group = (
        _field(spec, prepared, "x"),
        _field(spec, prepared, "y"),
        _field(spec, prepared, "group"),
    )
    y_all = [prepared.columns[item.column_index] for item in spec.fields if item.role == "y"]
    labels = {
        prepared.columns[item.column_index]: item.label or item.column for item in spec.fields
    }
    palette = cast(str, options.get("palette", "auto"))
    color_sequence = {
        "auto": list(theme.colorway),
        "plotly": px.colors.qualitative.Plotly,
        "d3": px.colors.qualitative.D3,
        "safe": px.colors.qualitative.Safe,
        "vivid": px.colors.qualitative.Vivid,
    }[palette]
    error = _field(spec, prepared, "error")
    error_lower = _field(spec, prepared, "error_lower")
    error_upper = _field(spec, prepared, "error_upper")
    error_plus = error or error_upper
    error_minus = None if error else error_lower
    try:
        if spec.chart_type == "table":
            selected = [
                prepared.columns[item.column_index]
                for item in spec.fields
                if item.role == "visible"
            ] or list(data.columns)
            display_labels = []
            for column in selected:
                column_index = next(
                    index
                    for index, internal_name in prepared.columns.items()
                    if internal_name == column
                )
                display_labels.append(str(frame.columns[column_index]))
            tokens = theme.tokens
            figure = go.Figure(
                go.Table(
                    header={
                        "values": display_labels,
                        "fill": {"color": tokens["surface_muted"]},
                        "font": {"color": tokens["text"]},
                        "line": {"color": tokens["border"]},
                    },
                    cells={
                        "values": [
                            data[column].where(data[column].notna(), "—") for column in selected
                        ],
                        "fill": {"color": tokens["surface"]},
                        "font": {"color": tokens["text"]},
                        "line": {"color": tokens["border"]},
                    },
                )
            )
        elif spec.chart_type == "bar":
            horizontal = options["orientation"] == "horizontal"
            figure = px.bar(
                data,
                x=y_all if horizontal else x,
                y=x if horizontal else y_all,
                color=group,
                orientation="h" if horizontal else "v",
                labels=labels,
                template=template,
                color_discrete_sequence=color_sequence,
                error_x=error_plus if horizontal else None,
                error_x_minus=error_minus if horizontal else None,
                error_y=None if horizontal else error_plus,
                error_y_minus=None if horizontal else error_minus,
            )
            figure.update_layout(
                barmode="stack" if options["bar_mode"] == "stacked" else "group",
                barnorm="percent" if options["normalize"] else None,
            )
        elif spec.chart_type == "line":
            figure = px.line(
                data,
                x=x,
                y=y_all,
                color=group,
                markers=bool(options["show_markers"]),
                labels=labels,
                template=template,
                color_discrete_sequence=color_sequence,
                error_y=error_plus,
                error_y_minus=error_minus,
            )
            if not options["show_lines"]:
                figure.update_traces(mode="markers")
        elif spec.chart_type == "area":
            figure = px.area(
                data,
                x=x,
                y=y_all,
                color=group,
                labels=labels,
                groupnorm="percent" if options["normalize"] else None,
                template=template,
                color_discrete_sequence=color_sequence,
            )
            if options["area_mode"] == "overlay":
                figure.update_traces(stackgroup=None, fill="tozeroy", opacity=0.55)
        elif spec.chart_type in ("scatter", "bubble"):
            size = _field(spec, prepared, "size") if spec.chart_type == "bubble" else None
            figure = px.scatter(
                data,
                x=x,
                y=y,
                color=group,
                size=size,
                labels=labels,
                opacity=float(cast(float | int, options.get("marker_opacity", 0.8))),
                template=template,
                color_discrete_sequence=color_sequence,
                error_y=error_plus,
                error_y_minus=error_minus,
            )
            if size:
                figure.update_traces(
                    marker={
                        "sizemode": options["size_mode"],
                        "sizeref": 1 / float(cast(float | int, options["size_coefficient"])),
                    }
                )
        elif spec.chart_type == "box":
            value, category = _field(spec, prepared, "value"), _field(spec, prepared, "category")
            horizontal = options["orientation"] == "horizontal"
            points = False if options["show_points"] == "none" else options["show_points"]
            figure = px.box(
                data,
                x=value if horizontal else category,
                y=category if horizontal else value,
                color=group,
                points=points,
                orientation="h" if horizontal else "v",
                labels=labels,
                template=template,
                color_discrete_sequence=color_sequence,
            )
        elif spec.chart_type == "pie":
            figure = px.pie(
                data,
                names=_field(spec, prepared, "category"),
                values=_field(spec, prepared, "value"),
                hole=float(cast(float | int, options["hole"])),
                labels=labels,
                template=template,
                color_discrete_sequence=color_sequence,
            )
            textinfo = {
                "label": "label",
                "value": "value",
                "percent": "percent",
                "label_percent": "label+percent",
            }[cast(str, options["label_content"])]
            figure.update_traces(textinfo=textinfo)
        elif spec.chart_type == "histogram":
            figure = px.histogram(
                data,
                x=_field(spec, prepared, "value"),
                color=group,
                nbins=int(cast(int, options["bin_count"])),
                barmode="stack" if options["histogram_mode"] == "stack" else "overlay",
                labels=labels,
                template=template,
                color_discrete_sequence=color_sequence,
            )
        elif spec.chart_type == "heatmap":
            figure = go.Figure(
                go.Heatmap(
                    z=data.to_numpy(),
                    x=list(data.columns),
                    y=list(data.index),
                    colorscale=options["colorscale"],
                    reversescale=bool(options["reverse_scale"]),
                    colorbar={
                        "title": labels.get(cast(str, _field(spec, prepared, "color")), "Value")
                    },
                )
            )
        elif spec.chart_type == "combo":
            figure = go.Figure()
            for binding in [item for item in spec.fields if item.role == "y"]:
                key = prepared.columns[binding.column_index]
                trace_cls = go.Bar if binding.trace_type == "bar" else go.Scatter
                kwargs = {
                    "x": data[x],
                    "y": data[key],
                    "name": binding.label or binding.column,
                    "yaxis": "y2" if binding.axis == "right" else "y",
                }
                if binding.trace_type == "line":
                    kwargs["mode"] = "lines+markers"
                figure.add_trace(trace_cls(**kwargs))
            if any(item.axis == "right" for item in spec.fields if item.role == "y"):
                figure.update_layout(yaxis2={"overlaying": "y", "side": "right"})
        elif spec.chart_type == "counter":
            value_binding = next(item for item in spec.fields if item.role == "value")
            value_row = int(cast(int, options["value_row"]))
            if value_row >= len(data):
                raise VisualizationConfigError(
                    "row is outside the filtered result", path="options.value_row"
                )
            value = data[prepared.columns[value_binding.column_index]].iloc[value_row]
            target_bindings = [item for item in spec.fields if item.role == "target"]
            indicator: dict[str, Any] = {
                "mode": "number",
                "value": value,
                "title": {"text": title or value_binding.label or value_binding.column},
            }
            if target_bindings:
                target_row = int(cast(int, options["target_row"]))
                if target_row >= len(data):
                    raise VisualizationConfigError(
                        "row is outside the filtered result", path="options.target_row"
                    )
                reference = data[prepared.columns[target_bindings[0].column_index]].iloc[target_row]
                indicator.update(
                    mode="number+delta",
                    delta={
                        "reference": reference,
                        "relative": options["comparison"] in ("relative", "percent"),
                        "valueformat": ".1%" if options["comparison"] == "percent" else None,
                    },
                )
            figure = go.Figure(go.Indicator(**indicator))
        else:
            raise VisualizationConfigError("unsupported chart type", path="chart_type")
        tokens = theme.tokens
        legend_position = cast(str, options.get("legend_position", "right"))
        legend_layout = {
            "right": {"orientation": "v", "x": 1.02, "y": 1.0},
            "left": {"orientation": "v", "x": -0.02, "xanchor": "right", "y": 1.0},
            "top": {"orientation": "h", "x": 0.0, "y": 1.12},
            "bottom": {"orientation": "h", "x": 0.0, "y": -0.2},
            "hidden": {},
        }[legend_position]
        x_scale = None if options.get("x_scale") == "auto" else options.get("x_scale")
        y_scale = None if options.get("y_scale") == "auto" else options.get("y_scale")
        figure.update_layout(
            template=template,
            paper_bgcolor=tokens["background"],
            plot_bgcolor=tokens["surface"],
            font={"color": tokens["text"], "family": theme.font_family},
            hoverlabel={
                "bgcolor": tokens["surface_raised"],
                "font": {"color": tokens["text"]},
                "bordercolor": tokens["border"],
            },
            title=title,
            showlegend=options.get("legend_position") != "hidden",
            legend={
                "traceorder": options.get("legend_order", "normal"),
                **legend_layout,
            },
            xaxis={
                "title": options.get("x_label"),
                "visible": options.get("show_x_axis", True),
                "type": x_scale,
                "color": tokens["text"],
                "linecolor": tokens["border"],
                "gridcolor": tokens["border"],
            },
            yaxis={
                "title": options.get("y_label"),
                "visible": options.get("show_y_axis", True),
                "type": y_scale,
                "color": tokens["text"],
                "linecolor": tokens["border"],
                "gridcolor": tokens["border"],
            },
        )
        if options.get("show_data_labels"):
            number_format = options.get("number_format") or ""
            figure.update_traces(
                texttemplate=f"%{{y:{number_format}}}",
                textposition="auto",
                selector=lambda trace: trace.type in ("bar", "scatter"),
            )
        if theme.kind == "high_contrast":
            dashes = ("solid", "dash", "dot", "dashdot")
            symbols = ("circle", "square", "diamond", "cross", "x")
            patterns = ("", "/", "\\", "x", ".")
            for index, trace in enumerate(figure.data):
                if isinstance(trace, go.Scatter):
                    trace.line.dash = dashes[index % len(dashes)]
                    trace.marker.symbol = symbols[index % len(symbols)]
                if isinstance(trace, go.Bar):
                    trace.marker.pattern.shape = patterns[index % len(patterns)]
                if isinstance(trace, go.Pie):
                    trace.marker.line = {"color": theme.tokens["text"], "width": 2}
                    trace.textinfo = "label+percent"
        if spec.plotly_overrides:
            try:
                if spec.plotly_overrides.trace:
                    figure.update_traces(**spec.plotly_overrides.trace)
                if spec.plotly_overrides.layout:
                    figure.update_layout(**spec.plotly_overrides.layout)
            except Exception as exc:
                raise VisualizationConfigError(
                    "Plotly rejected this override", path="plotly_overrides"
                ) from exc
        figure.update_layout(
            meta={
                "rn_row_counts": {
                    "source": prepared.source_rows,
                    "filtered": prepared.filtered_rows,
                    "plotted": prepared.plotted_rows,
                }
            }
        )
        return figure
    except VisualizationConfigError:
        raise
    except Exception as exc:
        raise VisualizationRenderError("The visualization could not be rendered.") from exc


__all__ = [
    "ColumnInfo",
    "PreparedData",
    "build_figure",
    "classify_columns",
    "infer_visualization",
    "prepare_data",
    "validate_visualization",
]
