"""Interactive visual QA lab for the production visualization workspace."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import ipywidgets as widgets
import pandas as pd

from sql_notebook_kit.results import NotebookResult
from sql_notebook_kit.visualize import (
    FieldBinding,
    ThemeContext,
    VisualizationCollection,
    VisualizationManager,
    VisualizationSpec,
    VisualizationWorkspace,
)

ThemeName = Literal["light", "dark", "high_contrast"]

LAB_CSS = """
<style>
.snk-lab {
  --snk-lab-panel: #f6f8fa;
  --snk-lab-border: #d0d7de;
  --snk-lab-text: #1f2328;
  color: var(--snk-lab-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.snk-lab > .widget-html:first-child { margin-bottom: 12px; }
.snk-lab-toolbar {
  background: var(--snk-lab-panel);
  border: 1px solid var(--snk-lab-border);
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 14px;
}
.snk-lab-toolbar-row { align-items: end; gap: 8px; flex-wrap: wrap; }
.snk-lab-toolbar-row > .widget-inline-hbox { min-width: 12rem; }
.snk-lab-status { min-height: 1.5rem; margin: 4px 0 0; }
.snk-lab-frame {
  background: #ffffff;
  border: 1px solid #d0d7de;
  box-shadow: 0 2px 8px rgb(0 0 0 / 12%);
  margin: 0 auto;
  overflow: auto;
  padding: 16px;
  transition: width 120ms ease;
}
.snk-lab-frame.snk-lab-theme-dark,
.snk-lab-frame.snk-lab-theme-high-contrast {
  background: #1e1e1e;
  border-color: #5a5a5a;
}
.snk-lab-frame.snk-lab-theme-dark .snk-viz-workspace,
.snk-lab-frame.snk-lab-theme-high-contrast .snk-viz-workspace {
  --snk-bg: #1e1e1e; --snk-surface: #252526; --snk-surface-muted: #313131;
  --snk-surface-raised: #2d2d30; --snk-text: #f0f0f0; --snk-text-muted: #c4c4c4;
  --snk-border: #5a5a5a; --snk-accent: #4daafc; --snk-accent-hover: #75beff;
  --snk-focus: #75beff; --snk-danger: #f48771; --snk-warning-bg: #3b2e00;
  --snk-warning-text: #ffd866; --snk-selection-bg: #063b49; --snk-input-bg: #313131;
}
.snk-lab-frame.snk-lab-theme-high-contrast .snk-viz-workspace {
  border: 1px solid #f0f0f0;
}
.snk-lab-frame.snk-lab-zoom-200 > .snk-viz-workspace {
  width: 50%;
  zoom: 2;
}
@media (max-width: 700px) {
  .snk-lab-frame { padding: 8px; }
}
</style>
"""


class MockFrontendBridge:
    """Deferred in-memory implementation of the production frontend contract."""

    deferred = True

    def __init__(self, collection: VisualizationCollection) -> None:
        self.available = True
        self.reason: str | None = None
        self.theme = ThemeContext.fallback("light")
        self.persisted = collection
        self.last_collection: VisualizationCollection | None = None
        self.last_expected_revision: int | None = None
        self._response_handler: Callable[[dict[str, Any]], None] | None = None
        self._state_listeners: list[Callable[[], None]] = []
        self._theme_listeners: list[Callable[[ThemeContext], None]] = []

    def set_response_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._response_handler = handler

    def subscribe_state(self, handler: Callable[[], None]) -> None:
        self._state_listeners.append(handler)

    def subscribe_theme(self, handler: Callable[[ThemeContext], None]) -> None:
        self._theme_listeners.append(handler)

    def load(self) -> VisualizationCollection:
        return self.persisted

    def save(
        self, collection: VisualizationCollection, *, expected_revision: int
    ) -> int:
        self.last_collection = collection
        self.last_expected_revision = expected_revision
        return expected_revision + 1

    def set_availability(self, mode: str) -> None:
        if mode == "saved":
            self.available = True
            self.reason = None
        elif mode == "connecting":
            self.available = False
            self.reason = "Connecting to the simulated VS Code metadata companion."
        else:
            self.available = False
            self.reason = "The simulated notebook is read-only; changes are session-only."
        if self._response_handler is not None:
            self._response_handler(
                {
                    "operation": "capabilities_result",
                    "payload": {"persistence": self.available, "reason": self.reason},
                }
            )
        for listener in tuple(self._state_listeners):
            listener()

    def set_theme(self, kind: ThemeName) -> None:
        self.theme = ThemeContext.fallback(kind)
        for listener in tuple(self._theme_listeners):
            listener(self.theme)

    def acknowledge(self) -> bool:
        if self.last_collection is None or self._response_handler is None:
            return False
        revision = (self.last_expected_revision or 0) + 1
        self.persisted = self.last_collection
        self._response_handler({"operation": "save_result", "payload": {"revision": revision}})
        self.last_collection = None
        self.last_expected_revision = None
        return True

    def conflict(self) -> bool:
        if self.last_collection is None or self._response_handler is None:
            return False
        self._response_handler(
            {
                "operation": "save_result",
                "payload": {"conflict": True, "collection": self.persisted.to_dict()},
            }
        )
        self.last_collection = None
        self.last_expected_revision = None
        return True

    def fail(self) -> bool:
        if self.last_collection is None or self._response_handler is None:
            return False
        self._response_handler(
            {"operation": "error", "payload": {"message": "Simulated metadata save failed."}}
        )
        self.last_collection = None
        self.last_expected_revision = None
        return True


@dataclass(frozen=True)
class Scenario:
    label: str
    frame: pd.DataFrame
    collection: VisualizationCollection = VisualizationCollection()
    truncated: bool = False


def _standard_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": pd.to_datetime(
                ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"] * 2,
                utc=True,
            ),
            "region": ["North"] * 4 + ["South"] * 4,
            "revenue": [120_000, 132_000, 128_000, 151_000, 98_000, 105_000, 117_000, 125_000],
            "orders": [410, 438, 429, 492, 352, 371, 401, 427],
            "margin": [0.31, 0.32, 0.30, 0.34, 0.27, 0.28, 0.29, 0.30],
        }
    )


def _saved_collection() -> VisualizationCollection:
    revenue = VisualizationSpec.create(
        "Revenue by region",
        "bar",
        fields=(
            FieldBinding("x", "region", 1),
            FieldBinding("y", "revenue", 2, aggregation="sum"),
        ),
        options={"title": "Revenue by region", "bar_mode": "grouped"},
    )
    trend = VisualizationSpec.create(
        "Monthly trend",
        "line",
        fields=(
            FieldBinding("x", "month", 0, date_grain="month"),
            FieldBinding("y", "revenue", 2, aggregation="sum"),
        ),
        options={"title": "Monthly revenue", "show_lines": True, "show_markers": True},
    )
    return VisualizationCollection(1, 4, trend.id, (revenue, trend))


def _scenarios() -> dict[str, Scenario]:
    standard = _standard_frame()
    missing = standard.copy()
    missing.loc[1, "revenue"] = None
    missing.loc[5, "margin"] = None
    empty = standard.iloc[:0].copy()
    stale = VisualizationSpec.create(
        "Stale binding",
        "scatter",
        fields=(FieldBinding("x", "removed_x", 8), FieldBinding("y", "removed_y", 9)),
    )
    return {
        "fresh": Scenario("Fresh table", standard),
        "saved": Scenario("Existing visualizations", standard, _saved_collection()),
        "truncated": Scenario(
            "Truncated result", standard, _saved_collection(), truncated=True
        ),
        "missing": Scenario("Missing values", missing, _saved_collection()),
        "empty": Scenario("Empty result", empty),
        "invalid": Scenario(
            "Invalid saved binding",
            standard,
            VisualizationCollection(1, 2, stale.id, (stale,)),
        ),
    }


class VisualizationLab:
    def __init__(self) -> None:
        self.scenarios = _scenarios()
        self.scenario = widgets.Dropdown(
            description="Scenario",
            options=[(item.label, key) for key, item in self.scenarios.items()],
            value="fresh",
        )
        self.theme = widgets.Dropdown(
            description="Theme",
            options=[("Light", "light"), ("Dark", "dark"), ("High contrast", "high_contrast")],
            value="light",
        )
        self.width = widgets.Dropdown(
            description="Frame",
            options=[("Desktop (1100 px)", "1100px"), ("Narrow (640 px)", "640px")],
            value="1100px",
        )
        self.zoom = widgets.ToggleButtons(
            description="Zoom", options=[("100%", "100"), ("200%", "200")]
        )
        self.persistence = widgets.Dropdown(
            description="Persistence",
            options=[
                ("Saved / writable", "saved"),
                ("Connecting", "connecting"),
                ("Session-only", "session_only"),
            ],
            value="saved",
        )
        self.ack = widgets.Button(description="Acknowledge save", icon="check")
        self.conflict = widgets.Button(description="Inject conflict", icon="warning")
        self.failure = widgets.Button(description="Fail save", icon="times")
        self.reset = widgets.Button(description="Reset workspace", icon="refresh")
        self.status = widgets.HTML(
            '<div class="snk-lab-status" role="status" aria-live="polite">Lab ready.</div>'
        )
        self.frame = widgets.VBox()
        self.frame.add_class("snk-lab-frame")

        first_row = widgets.HBox([self.scenario, self.theme, self.width, self.zoom])
        first_row.add_class("snk-lab-toolbar-row")
        second_row = widgets.HBox(
            [self.persistence, self.ack, self.conflict, self.failure, self.reset]
        )
        second_row.add_class("snk-lab-toolbar-row")
        toolbar = widgets.VBox([first_row, second_row, self.status])
        toolbar.add_class("snk-lab-toolbar")
        heading = widgets.HTML(
            "<h2>SQL Notebook Kit visualization lab</h2>"
            "<p>Production widgets with a simulated VS Code theme and metadata companion.</p>"
        )
        self.root = widgets.VBox([widgets.HTML(LAB_CSS), heading, toolbar, self.frame])
        self.root.add_class("snk-lab")

        self.scenario.observe(self._rebuild, names="value")
        self.theme.observe(self._change_theme, names="value")
        self.width.observe(self._change_width, names="value")
        self.zoom.observe(self._change_zoom, names="value")
        self.persistence.observe(self._change_persistence, names="value")
        self.ack.on_click(self._acknowledge)
        self.conflict.on_click(self._inject_conflict)
        self.failure.on_click(self._fail_save)
        self.reset.on_click(self._rebuild)
        self._rebuild()

    def _message(self, value: str) -> None:
        self.status.value = (
            f'<div class="snk-lab-status" role="status" aria-live="polite">{value}</div>'
        )

    def _rebuild(self, _change: Any = None) -> None:
        scenario = self.scenarios[self.scenario.value]
        result = NotebookResult(
            scenario.frame.copy(), raw=None, truncated=scenario.truncated, max_rows=10_000
        )
        self.bridge = MockFrontendBridge(scenario.collection)
        manager = VisualizationManager(result, collection=scenario.collection, bridge=self.bridge)
        result._visualizations = manager
        self.workspace = VisualizationWorkspace(result)
        self.frame.children = (self.workspace.root,)
        self._change_width()
        self._change_zoom()
        self._change_theme()
        self._change_persistence()
        self._message(f"Loaded {scenario.label}.")

    def _change_theme(self, _change: Any = None) -> None:
        for name in ("light", "dark", "high-contrast"):
            self.frame.remove_class(f"snk-lab-theme-{name}")
        theme = str(self.theme.value)
        self.frame.add_class(f"snk-lab-theme-{theme.replace('_', '-')}")
        self.bridge.set_theme(theme)  # type: ignore[arg-type]

    def _change_width(self, _change: Any = None) -> None:
        self.frame.layout.width = str(self.width.value)
        self.frame.layout.max_width = "100%"

    def _change_zoom(self, _change: Any = None) -> None:
        self.frame.remove_class("snk-lab-zoom-200")
        if self.zoom.value == "200":
            self.frame.add_class("snk-lab-zoom-200")

    def _change_persistence(self, _change: Any = None) -> None:
        self.bridge.set_availability(str(self.persistence.value))

    def _acknowledge(self, _button: Any) -> None:
        self._message(
            "Save acknowledged." if self.bridge.acknowledge() else "Make a workspace change first."
        )

    def _inject_conflict(self, _button: Any) -> None:
        self._message(
            "Conflict injected." if self.bridge.conflict() else "Make a workspace change first."
        )

    def _fail_save(self, _button: Any) -> None:
        self._message(
            "Save failure injected." if self.bridge.fail() else "Make a workspace change first."
        )


def build_lab() -> widgets.Widget:
    """Build a fresh interactive lab suitable for Voilà or a notebook cell."""
    return VisualizationLab().root


__all__ = ["MockFrontendBridge", "VisualizationLab", "build_lab"]
