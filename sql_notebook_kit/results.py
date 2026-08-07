"""Detached, bounded notebook results."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sql_notebook_kit.errors import MissingOptionalDependencyError

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
    cell_id: str | None = None
    visualization_metadata: dict[str, Any] | None = None
    lazy_notice: str | None = None
    visualization_enabled: bool = True
    _visualizations: Any = field(default=None, init=False, repr=False)
    _workspace: Any = field(default=None, init=False, repr=False)

    @property
    def visualizations(self) -> Any:
        """Return this result's lazily created visualization collection manager."""
        if self._visualizations is None:
            try:
                from sql_notebook_kit.visualize import VisualizationManager
            except ImportError as exc:
                raise MissingOptionalDependencyError(
                    "visualization requires 'sql-notebook-kit[viz]'"
                ) from exc
            self._visualizations = VisualizationManager(self)
        return self._visualizations

    def visualize(self, id_or_name: str | None = None) -> Any:
        """Build the workspace and optionally activate a named visualization."""
        try:
            from sql_notebook_kit.visualize import build_workspace
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "visualization requires 'sql-notebook-kit[viz]'"
            ) from exc
        if id_or_name is not None:
            self.visualizations.activate(id_or_name)
        if self._workspace is None:
            try:
                self._workspace = build_workspace(self)
            except ImportError as exc:
                raise MissingOptionalDependencyError(
                    "visualization requires 'sql-notebook-kit[viz]'"
                ) from exc
        return self._workspace

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
                "<div class='snk-result-warning'>"
                f"Result truncated to {self.max_rows:,} local rows. Visual filters and "
                "aggregations do not include unfetched rows.</div>"
            )
        lazy_footer = (
            "<div class='snk-lazy-notice' "
            "style='color:var(--jp-ui-font-color2,GrayText);font-size:0.8rem;'>"
            "<em>"
            f"{html.escape(self.lazy_notice)}</em></div>"
            if self.lazy_notice
            else ""
        )
        return banner + self.dataframe.head(100).to_html(index=False) + lazy_footer

    def _ipython_display_(self) -> None:
        from IPython.display import HTML, display

        if self.visualization_enabled:
            try:
                display(self.visualize())
                return
            except MissingOptionalDependencyError:
                pass
        display(HTML(self._repr_html_()))
