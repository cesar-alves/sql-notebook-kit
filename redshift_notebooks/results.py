"""Detached, bounded notebook results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from redshift_notebooks.errors import MissingOptionalDependencyError

if TYPE_CHECKING:
    import pandas as pd


@dataclass(slots=True)
class NotebookResult:
    """A bounded DataFrame plus the JupySQL result that produced it.

    ``truncated`` means more rows were available from the cursor than are held
    locally. Visual filters and aggregations therefore apply only to
    :attr:`dataframe`, never silently to unfetched warehouse rows.
    """

    dataframe: pd.DataFrame
    raw: Any
    truncated: bool = False
    max_rows: int = 10_000
    chart: Any = None

    def visualize(self, spec: Any = None) -> Any:
        """Build an interactive Plotly/ipywidgets editor for this result."""
        try:
            from redshift_notebooks.visualize import ChartSpec, build_chart_builder
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "visualization requires 'redshift-notebooks[viz]'"
            ) from exc
        if spec is None:
            spec = ChartSpec.infer(self.dataframe)
        self.chart = build_chart_builder(self, spec)
        return self.chart

    def to_csv(self, path: str | Path | None = None, **kwargs: Any) -> str | None:
        """Export the bounded local data, never rows that were not fetched."""
        if path is None:
            return self.dataframe.to_csv(index=False, **kwargs)
        self.dataframe.to_csv(path, index=False, **kwargs)
        return None

    def _repr_html_(self) -> str:
        banner = ""
        if self.truncated:
            banner = (
                "<div style='padding:8px;background:#fff3cd;border:1px solid #ffe69c'>"
                f"Result truncated to {self.max_rows:,} local rows. Visual filters and "
                "aggregations do not include unfetched rows.</div>"
            )
        return banner + self.dataframe.head(100).to_html(index=False)

    def _ipython_display_(self) -> None:
        from IPython.display import display

        try:
            display(self.visualize())
        except MissingOptionalDependencyError:
            display(self.dataframe)
