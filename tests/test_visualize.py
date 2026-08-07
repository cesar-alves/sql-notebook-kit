import base64
import json
import uuid
from dataclasses import replace
from importlib.resources import files

import pandas as pd
import plotly.io as pio
import pytest
from plotly.io import _renderers

from sql_notebook_kit.errors import VisualizationConfigError
from sql_notebook_kit.results import NotebookResult
from sql_notebook_kit.visualize import (
    FieldBinding,
    FilterSpec,
    ThemeContext,
    VisualizationCollection,
    VisualizationSpec,
    VisualizationWorkspace,
    build_figure,
    build_plotly_template,
    infer_visualization,
    list_visualization_definitions,
    prepare_data,
)
from sql_notebook_kit.visualize.workspace import _copy_frame, _frame_tsv, _table_html


def test_workspace_root_is_unframed_except_in_forced_colors():
    css = files("sql_notebook_kit.visualize").joinpath("workspace.css").read_text()
    root_rule = css.split("}", maxsplit=1)[0]
    forced_colors = css.split("@media (forced-colors: active)", maxsplit=1)[1]

    assert "border: 0; border-radius: 0; padding: 8px;" in root_rule
    assert "border: 1px solid var(--snk-border)" not in root_rule
    assert "border: 1px solid CanvasText" in forced_colors


def binding(role, column, index, **kwargs):
    return FieldBinding(role, column, index, **kwargs)


def spec(chart_type="table", fields=(), **kwargs):
    return VisualizationSpec(1, str(uuid.uuid4()), "Example", chart_type, fields, **kwargs)


def test_workspace_uses_tab_strip_muted_footer_and_contextual_actions(monkeypatch):
    monkeypatch.setattr("IPython.display.display", lambda *_args, **_kwargs: None)
    result = NotebookResult(pd.DataFrame({"category": ["alpha"], "amount": [1]}), raw=None)
    workspace = VisualizationWorkspace(result)

    assert workspace.tabs.description == ""
    assert tuple(workspace.tabs.options) == (("Table", ""),)
    assert workspace.add_button.description == "+"
    assert workspace.add_button.tooltip == "Add visualization"
    assert workspace.context_actions.layout.display == "flex"
    assert workspace.copy_button.description == "Copy table"
    assert workspace.export_button.layout.display == "none"
    assert workspace.root.children.index(workspace.toolbar) < workspace.root.children.index(
        workspace.body
    )
    assert workspace.root.children.index(workspace.body) < workspace.root.children.index(
        workspace.notice
    )
    assert "snk-row-notice" in workspace.notice.value
    assert "snk-export-button" in workspace.export_button._dom_classes
    assert "snk-export-status" in workspace.export_status.value

    chart = spec("histogram", (binding("value", "amount", 1),))
    result.visualizations.add(chart, persist=False)
    workspace._refresh_tabs()
    workspace._show_active()

    assert workspace.context_actions.layout.display == "flex"
    assert [button.description for button in workspace.context_actions.children] == [
        "Copy data",
        "Export PNG",
        "Edit",
        "Rename",
        "Duplicate",
        "Delete",
    ]
    workspace.tabs.value = ""
    assert workspace.context_actions.layout.display == "flex"
    assert workspace.copy_button.description == "Copy table"
    assert workspace.export_button.layout.display == "none"


def test_copy_frame_uses_prepared_render_fields_and_display_labels():
    frame = pd.DataFrame(
        {
            "month": pd.to_datetime(["2026-01-01", "2026-01-20", "2026-02-01"]),
            "region": ["west", "west", "east"],
            "amount": [1, 2, 10],
            "filter_only": [True, True, False],
        }
    )
    chart = spec(
        "bar",
        (
            binding("x", "month", 0, label="Period", date_grain="month"),
            binding("y", "amount", 2, label="Revenue", aggregation="sum"),
        ),
        filters=(FilterSpec("filter_only", 3, "equals", True),),
        options={"sort_by": "amount", "sort_direction": "descending", "limit": 1},
    )

    copied, prepared = _copy_frame(frame, chart)

    assert prepared.source_rows == 3
    assert prepared.filtered_rows == 2
    assert list(copied.columns) == ["Period", "Revenue"]
    assert copied.iloc[0].tolist() == [pd.Timestamp("2026-01-01"), 3]


def test_copy_frame_exports_heatmap_matrix_with_axis_labels():
    frame = pd.DataFrame({"x": ["a", "b"], "y": ["one", "one"], "value": [1, 2]})
    chart = spec(
        "heatmap",
        (
            binding("x", "x", 0),
            binding("y", "y", 1, label="Row"),
            binding("color", "value", 2),
        ),
    )

    copied, _prepared = _copy_frame(frame, chart)

    assert list(copied.columns) == ["Row", "a", "b"]
    assert copied.iloc[0].tolist() == ["one", 1.0, 2.0]


def test_tsv_and_copy_table_markup_preserve_special_values_safely():
    frame = pd.DataFrame(
        [["a\tb", 'say "hello"', "line one\nline two", None, [1, 2]]],
        columns=["first", "quote", "multiline", "missing", 7],
    )

    assert _frame_tsv(frame) == (
        'first\tquote\tmultiline\tmissing\t7\n'
        '"a\tb"\t"say ""hello"""\t"line one\nline two"\t\t[1, 2]'
    )
    rendered = _table_html(frame, label='Query "result"')
    assert 'aria-label="Query &quot;result&quot;"' in rendered
    assert 'data-snk-null="true">—</td>' in rendered
    assert "<script" not in rendered


def test_editor_name_and_options_controls_have_theme_hooks(monkeypatch):
    monkeypatch.setattr("IPython.display.display", lambda *_args, **_kwargs: None)
    result = NotebookResult(pd.DataFrame({"category": ["alpha"], "amount": [1]}), raw=None)
    workspace = VisualizationWorkspace(result)
    chart = spec("histogram", (binding("value", "amount", 1),))

    workspace._open_editor(chart, creating=True)

    assert "snk-name-control" in workspace.name_control._dom_classes
    assert "snk-options-section" in workspace.option_box.children[0]._dom_classes


def test_workspace_css_covers_intrinsic_tables_and_dark_editor_controls():
    css = files("sql_notebook_kit.visualize").joinpath("workspace.css").read_text()

    assert "table-layout: auto; width: max-content; min-width: 100%;" in css
    assert ".snk-row-notice" in css
    assert "color: var(--snk-text-muted)" in css
    assert ".snk-name-control input" in css
    assert ".snk-options-section .lm-AccordionPanel-title" in css
    assert ".jupyter-widget-Collapse-header" in css
    assert "--jp-widgets-input-background-color: var(--snk-input-bg)" in css
    assert "select option { color-scheme: dark; }" in css
    assert ".snk-dialog-panel" in css
    assert "background: var(--snk-surface-muted) !important" in css
    assert ".snk-viz-workspace.snk-theme-dark" in css


def test_inference_uses_documented_priority_and_positions():
    frame = pd.DataFrame(
        {
            "occurred_at": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
            "category": ["a", "b"],
            "amount": [1, 2],
        }
    )
    inferred = infer_visualization(frame)
    assert inferred.chart_type == "line"
    assert [(item.role, item.column_index) for item in inferred.fields] == [("x", 0), ("y", 2)]


def test_public_specs_round_trip_and_reject_unknown_or_non_finite_values():
    original = spec(
        "bar",
        (binding("x", "category", 0), binding("y", "amount", 1, aggregation="sum")),
        filters=(FilterSpec("category", 0, "in", ["a", "b"]),),
        options={"limit": 10},
    )
    assert VisualizationSpec.from_json(original.to_json()) == original
    value = json.loads(original.to_json())
    value["unknown"] = True
    with pytest.raises(VisualizationConfigError, match="unknown key"):
        VisualizationSpec.from_dict(value)
    with pytest.raises(VisualizationConfigError, match="finite"):
        replace(original, options={"value": float("nan")})


def test_collection_validation_and_size_constraints():
    item = spec()
    collection = VisualizationCollection(1, 2, item.id, (item,))
    assert VisualizationCollection.from_json(collection.to_json()) == collection
    with pytest.raises(VisualizationConfigError, match="IDs must be unique"):
        VisualizationCollection(1, 0, None, (item, item))


def test_registry_has_unique_complete_phase_one_types():
    definitions = list_visualization_definitions()
    assert {item.id for item in definitions} == {
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
    assert len(definitions) == len({item.id for item in definitions})


def test_prepare_data_filters_buckets_aggregates_sorts_limits_without_mutation():
    frame = pd.DataFrame(
        {
            "when": pd.to_datetime(["2026-01-01", "2026-01-15", "2026-02-01"]),
            "amount": pd.array([1, 2, 10], dtype="Int64"),
        }
    )
    original = frame.copy()
    chart = spec(
        "line",
        (
            binding("x", "when", 0, date_grain="month"),
            binding("y", "amount", 1, aggregation="sum"),
        ),
        filters=(FilterSpec("amount", 1, "greater_or_equal", 2),),
        options={
            "missing_value_policy": "hide",
            "sort_by": "amount",
            "sort_direction": "descending",
            "limit": 1,
        },
    )
    prepared = prepare_data(frame, chart)
    assert prepared.source_rows == 3
    assert prepared.filtered_rows == 2
    assert prepared.plotted_rows == 1
    assert prepared.frame.iloc[0, -1] == 10
    pd.testing.assert_frame_equal(frame, original)


def test_literal_string_filter_and_duplicate_non_string_column_resolution():
    frame = pd.DataFrame([["a.b", 1, 2], ["axb", 3, 4]], columns=[7, "value", "value"])
    chart = spec(
        "table",
        (binding("visible", "value", 2),),
        filters=(FilterSpec("7", 0, "contains", "."),),
        options={},
    )
    prepared = prepare_data(frame, chart)
    assert prepared.frame.iloc[:, 0].tolist() == ["a.b"]
    assert prepared.frame.iloc[:, 1].tolist() == [2]
    with pytest.raises(VisualizationConfigError, match="moved or was replaced"):
        prepare_data(frame.iloc[:, [1, 0, 2]], chart)


def test_manager_crud_import_and_session_dirty_fallback():
    result = NotebookResult(pd.DataFrame({"value": [1]}), raw=None)
    first = spec("histogram", (binding("value", "value", 0),))
    result.visualizations.add(first)
    assert result.visualizations.get(first.id) == first
    assert result.visualizations.dirty
    renamed = result.visualizations.rename(first.id, "Renamed")
    copied = result.visualizations.duplicate(renamed.id)
    assert copied.name == "Renamed copy"
    exported = result.visualizations.export_json()
    other = NotebookResult(pd.DataFrame({"value": [1]}), raw=None)
    imported = other.visualizations.import_json(exported)
    assert len(imported) == 2
    assert not {item.id for item in imported} & {renamed.id, copied.id}
    result.visualizations.delete(copied.id)
    assert result.visualizations.list() == (renamed,)


class DeferredBridge:
    available = True
    deferred = True
    reason = None

    def __init__(self):
        self.calls = []
        self.handler = None

    def set_response_handler(self, handler):
        self.handler = handler

    def subscribe_state(self, _handler):
        pass

    def save(self, collection, *, expected_revision):
        self.calls.append((collection, expected_revision))


def test_deferred_persistence_coalesces_edits_and_acknowledges_revisions():
    from sql_notebook_kit.visualize.manager import VisualizationManager

    bridge = DeferredBridge()
    result = NotebookResult(pd.DataFrame({"value": [1]}), raw=None)
    manager = VisualizationManager(result, bridge=bridge)
    first = spec("histogram", (binding("value", "value", 0),))
    manager.add(first)
    manager.rename(first.id, "Renamed")
    assert len(bridge.calls) == 1
    assert manager.dirty

    bridge.handler({"operation": "save_result", "payload": {"revision": 1}})
    assert len(bridge.calls) == 2
    assert bridge.calls[1][1] == 1
    bridge.handler({"operation": "save_result", "payload": {"revision": 2}})
    assert not manager.dirty
    assert manager.collection.revision == 2


def test_manager_restores_execute_request_metadata_and_preserves_conflict_draft():
    from sql_notebook_kit.visualize.manager import VisualizationManager

    saved = VisualizationCollection(1, 4, None, ())
    bridge = DeferredBridge()
    result = NotebookResult(
        pd.DataFrame({"value": [1]}), raw=None, visualization_metadata=saved.to_dict()
    )
    manager = VisualizationManager(result, bridge=bridge)
    first = spec("histogram", (binding("value", "value", 0),))
    manager.add(first)
    bridge.handler({
        "operation": "save_result",
        "payload": {"conflict": True, "collection": saved.to_dict()},
    })
    assert manager.persistence_state == "conflict"
    assert manager.list() == ()
    manager.reapply()
    assert manager.list() == (first,)


def test_vscode_bridge_accepts_versioned_callback_and_ignores_invalid_payload(monkeypatch):
    from sql_notebook_kit.visualize import protocol

    displayed = []
    timers = []

    class Timer:
        daemon = False

        def __init__(self, interval, callback):
            self.interval = interval
            self.callback = callback
            self.started = False
            self.cancelled = False
            timers.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

    monkeypatch.setattr(protocol.threading, "Timer", Timer)
    monkeypatch.setattr("IPython.display.display", lambda *args, **kwargs: displayed.append(args))
    monkeypatch.setattr(
        "IPython.display.update_display", lambda *args, **kwargs: displayed.append(args)
    )
    bridge = protocol.VscodePersistenceBridge("vscode-notebook-cell:/example#1")
    message = {
        "protocol_version": 1,
        "request_id": str(uuid.uuid4()),
        "session_id": bridge.session_id,
        "cell_id": bridge.cell_id,
        "operation": "capabilities_result",
        "payload": {"persistence": True},
    }
    encoded = base64.b64encode(json.dumps(message).encode()).decode()
    protocol._deliver_vscode_response(encoded)
    protocol._deliver_vscode_response(base64.b64encode(b"[]").decode())
    assert bridge.available
    assert bridge.reason is None
    assert len(displayed) == 2
    assert timers[0].interval == 45.0
    assert timers[0].started
    assert timers[0].cancelled


def _chart_spec(chart_type):
    if chart_type == "table":
        return spec(chart_type)
    roles = {
        "bar": (binding("x", "category", 0), binding("y", "a", 1)),
        "line": (binding("x", "category", 0), binding("y", "a", 1)),
        "area": (binding("x", "category", 0), binding("y", "a", 1)),
        "scatter": (binding("x", "a", 1), binding("y", "b", 2)),
        "bubble": (binding("x", "a", 1), binding("y", "b", 2), binding("size", "size", 3)),
        "box": (binding("value", "a", 1),),
        "pie": (binding("category", "category", 0), binding("value", "a", 1)),
        "histogram": (binding("value", "a", 1),),
        "heatmap": (
            binding("x", "category", 0),
            binding("y", "group", 4),
            binding("color", "a", 1),
        ),
        "combo": (
            binding("x", "category", 0),
            binding("y", "a", 1, trace_type="bar"),
            binding("y", "b", 2, trace_type="line", axis="right"),
        ),
        "counter": (binding("value", "a", 1), binding("target", "b", 2)),
    }[chart_type]
    return spec(chart_type, roles)


@pytest.mark.parametrize("chart_type", [item.id for item in list_visualization_definitions()])
def test_every_renderer_uses_explicit_theme_and_reports_counts(chart_type):
    frame = pd.DataFrame(
        {"category": ["a", "b"], "a": [1, 2], "b": [2, 3], "size": [4, 5], "group": ["x", "y"]}
    )
    figure = build_figure(frame, _chart_spec(chart_type), ThemeContext.fallback("dark"))
    assert figure.layout.paper_bgcolor == "#1e1e1e"
    assert figure.layout.meta["rn_row_counts"]["source"] == 2


def test_plotly_template_does_not_mutate_global_default():
    before = pio.templates.default
    template = build_plotly_template(ThemeContext.fallback("high_contrast"))
    assert template.layout.font.color == "#f0f0f0"
    assert pio.templates.default == before


def test_plotly_figure_renders_through_notebook_mime_path(monkeypatch):
    displayed = []
    monkeypatch.setattr(
        _renderers.ipython_display,
        "display",
        lambda bundle, raw: displayed.append((bundle, raw)),
    )
    frame = pd.DataFrame({"category": ["a", "b"], "a": [1, 2]})
    figure = build_figure(frame, _chart_spec("bar"), ThemeContext.fallback("light"))

    pio.show(figure, renderer="plotly_mimetype")

    assert len(displayed) == 1
    assert displayed[0][1] is True
    assert "application/vnd.plotly.v1+json" in displayed[0][0]


def test_notebook_result_exports_and_renders_pandas_data():
    frame = pd.DataFrame({"category": ["alpha", None], "amount": [1, 2]})
    result = NotebookResult(dataframe=frame, raw=None)
    assert result.to_csv() == "category,amount\nalpha,1\n,2\n"
    assert "alpha" in result._repr_html_()
