"""Metadata-backed, bounded Plotly visualization workspace."""

from redshift_notebooks.visualize.core import (
    ColumnInfo,
    PreparedData,
    build_figure,
    classify_columns,
    infer_visualization,
    prepare_data,
    validate_visualization,
)
from redshift_notebooks.visualize.manager import VisualizationManager
from redshift_notebooks.visualize.models import (
    Aggregation,
    ChartType,
    FieldBinding,
    FilterSpec,
    JSONValue,
    PlotlyOverrides,
    VisualizationCollection,
    VisualizationSpec,
)
from redshift_notebooks.visualize.protocol import COMM_TARGET, PROTOCOL_VERSION
from redshift_notebooks.visualize.registry import (
    ControlDefinition,
    FieldRoleDefinition,
    VisualizationDefinition,
    get_visualization_definition,
    list_visualization_definitions,
)
from redshift_notebooks.visualize.theme import ThemeContext, build_plotly_template
from redshift_notebooks.visualize.workspace import VisualizationWorkspace, build_workspace

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
