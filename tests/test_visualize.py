import base64
import json
import uuid
from dataclasses import replace

import pandas as pd
import plotly.io as pio
import pytest
from plotly.io import _renderers

from redshift_notebooks.errors import VisualizationConfigError
from redshift_notebooks.results import NotebookResult
from redshift_notebooks.visualize import (
    FieldBinding,
    FilterSpec,
    ThemeContext,
    VisualizationCollection,
    VisualizationSpec,
    build_figure,
    build_plotly_template,
    infer_visualization,
    list_visualization_definitions,
    prepare_data,
)


def binding(role, column, index, **kwargs):
    return FieldBinding(role, column, index, **kwargs)


def spec(chart_type="table", fields=(), **kwargs):
    return VisualizationSpec(1, str(uuid.uuid4()), "Example", chart_type, fields, **kwargs)


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
    from redshift_notebooks.visualize.manager import VisualizationManager

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
    from redshift_notebooks.visualize.manager import VisualizationManager

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
    from redshift_notebooks.visualize import protocol

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
