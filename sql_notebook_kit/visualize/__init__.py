"""Metadata-backed, bounded Plotly visualization workspace."""

from sql_notebook_kit.visualize.core import (
    ColumnInfo,
    PreparedData,
    build_figure,
    classify_columns,
    infer_visualization,
    prepare_data,
    validate_visualization,
)
from sql_notebook_kit.visualize.manager import VisualizationManager
from sql_notebook_kit.visualize.models import (
    Aggregation,
    ChartType,
    FieldBinding,
    FilterSpec,
    JSONValue,
    PlotlyOverrides,
    VisualizationCollection,
    VisualizationSpec,
)
from sql_notebook_kit.visualize.protocol import COMM_TARGET, PROTOCOL_VERSION
from sql_notebook_kit.visualize.registry import (
    ControlDefinition,
    FieldRoleDefinition,
    VisualizationDefinition,
    get_visualization_definition,
    list_visualization_definitions,
)
from sql_notebook_kit.visualize.theme import ThemeContext, build_plotly_template
from sql_notebook_kit.visualize.workspace import VisualizationWorkspace, build_workspace

__all__ = [
    "Aggregation",
    "COMM_TARGET",
    "ChartType",
    "ColumnInfo",
    "ControlDefinition",
    "FieldBinding",
    "FieldRoleDefinition",
    "FilterSpec",
    "JSONValue",
    "PlotlyOverrides",
    "PreparedData",
    "PROTOCOL_VERSION",
    "ThemeContext",
    "VisualizationCollection",
    "VisualizationDefinition",
    "VisualizationManager",
    "VisualizationSpec",
    "VisualizationWorkspace",
    "build_figure",
    "build_plotly_template",
    "build_workspace",
    "classify_columns",
    "get_visualization_definition",
    "infer_visualization",
    "list_visualization_definitions",
    "prepare_data",
    "validate_visualization",
]
