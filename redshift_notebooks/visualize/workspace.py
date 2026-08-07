"""Accessible ipywidgets workspace for visualization collections."""

from __future__ import annotations

import asyncio
import csv
import html
import io
from contextlib import suppress
from dataclasses import replace
from importlib.resources import files
from typing import Any, cast

from redshift_notebooks.errors import VisualizationError
from redshift_notebooks.visualize.core import (
    build_figure,
    classify_columns,
    infer_visualization,
    prepare_data,
    validate_visualization,
)
from redshift_notebooks.visualize.models import FieldBinding, VisualizationSpec
from redshift_notebooks.visualize.registry import (
    get_visualization_definition,
    list_visualization_definitions,
)

WORKSPACE_CSS = "<style>" + files(__package__).joinpath("workspace.css").read_text() + "</style>"


def _is_missing(value: Any) -> bool:
    import pandas as pd
    from pandas.api.types import is_scalar

    return bool(pd.isna(value)) if is_scalar(value) else False


def _cell_text(value: Any) -> str:
    return "" if _is_missing(value) else str(value)


def _frame_tsv(frame: Any) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(str(column) for column in frame.columns)
    writer.writerows(
        [_cell_text(value) for value in row]
        for row in frame.itertuples(index=False, name=None)
    )
    return output.getvalue().removesuffix("\n")


def _copy_frame(frame: Any, spec: VisualizationSpec) -> tuple[Any, Any]:
    """Return the rendered fields from the deterministic visualization preparation path."""
    prepared = prepare_data(frame, spec)
    if spec.chart_type == "heatmap":
        result = prepared.frame.reset_index()
        y_binding = next(item for item in spec.fields if item.role == "y")
        result.columns = [
            y_binding.label or y_binding.column,
            *(str(column) for column in prepared.frame.columns),
        ]
        return result, prepared

    if spec.chart_type == "table" and not spec.fields:
        bindings = [
            FieldBinding("visible", str(column), index)
            for index, column in enumerate(frame.columns)
        ]
    else:
        bindings = list(spec.fields)
    columns: list[str] = []
    labels: list[str] = []
    for binding in bindings:
        column = prepared.columns[binding.column_index]
        if column in columns or column not in prepared.frame:
            continue
        columns.append(column)
        labels.append(binding.label or binding.column)
    result = prepared.frame.loc[:, columns].copy()
    result.columns = labels
    return result, prepared


def _table_html(frame: Any, *, label: str) -> str:
    headers = "".join(
        f'<th scope="col" tabindex="{0 if index == 0 else -1}" '
        f'data-rn-row="0" data-rn-column="{index}">'
        f"{html.escape(str(column))}</th>"
        for index, column in enumerate(frame.columns)
    )
    rows: list[str] = []
    for row_index, row in enumerate(frame.itertuples(index=False, name=None), start=1):
        cells = []
        for column_index, value in enumerate(row):
            text = _cell_text(value)
            missing = _is_missing(value)
            display = "—" if missing else text
            null = ' data-rn-null="true"' if missing else ""
            cells.append(
                f'<td tabindex="-1" data-rn-row="{row_index}" '
                f'data-rn-column="{column_index}"{null}>{html.escape(display)}</td>'
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f'<div class="rn-table-wrap rn-copy-table"><table role="grid" '
        f'aria-label="{html.escape(label)}"><thead><tr>{headers}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _copy_payload(frame: Any) -> str:
    return (
        '<textarea class="rn-copy-payload" hidden readonly aria-hidden="true">'
        f"{html.escape(_frame_tsv(frame))}</textarea>"
    )


class VisualizationWorkspace:
    def __init__(self, result: Any) -> None:
        import ipywidgets as widgets

        self.result = result
        self.manager = result.visualizations
        self.theme = self.manager.theme
        self.manager.subscribe_theme(self._theme_changed)
        self.manager.subscribe_state(self._persistence_changed)
        self.widgets = widgets
        self._draft: VisualizationSpec | None = None
        self._drafts: dict[str, VisualizationSpec] = {}
        self._pending: asyncio.TimerHandle | None = None
        self._generation = 0
        self._updating_tabs = False
        self.css = widgets.HTML(WORKSPACE_CSS)
        rows = len(result.dataframe)
        message = (
            f"⚠ Result truncated to {rows:,} local rows; "
            "unfetched rows are excluded from all visualizations."
            if result.truncated
            else f"Using {rows:,} local rows."
        )
        self.notice = widgets.HTML(
            f'<div class="rn-row-notice" role="status">{html.escape(message)}</div>'
        )
        self.persistence = widgets.HTML()
        self.reapply_button = widgets.Button(
            description="Reapply changes", icon="refresh", layout=widgets.Layout(display="none")
        )
        self.reapply_button.on_click(self._reapply)
        self._persistence_changed()
        self.tabs = widgets.ToggleButtons()
        self.tabs.add_class("rn-tabs")
        self.tabs.observe(self._select_tab, names="value")
        self.add_button = widgets.Button(description="+", tooltip="Add visualization")
        self.add_button.add_class("rn-add-tab")
        self.add_button.on_click(self._open_add)
        self.copy_button = widgets.Button(
            description="Copy table",
            icon="copy",
            tooltip="Copy the complete bounded result as TSV",
        )
        self.copy_button.add_class("rn-copy-button")
        self.export_button = widgets.Button(
            description="Export PNG",
            icon="download",
            tooltip="Export rendered visualization as PNG",
        )
        self.export_button.add_class("rn-export-button")
        self.edit_button = widgets.Button(description="Edit", icon="edit", tooltip="Edit")
        self.rename_button = widgets.Button(
            description="Rename", icon="pencil", tooltip="Rename"
        )
        self.duplicate_button = widgets.Button(
            description="Duplicate", icon="copy", tooltip="Duplicate"
        )
        self.delete_button = widgets.Button(
            description="Delete", icon="trash", tooltip="Delete"
        )
        self.edit_button.on_click(self._edit_active)
        self.rename_button.on_click(self._rename_active)
        self.duplicate_button.on_click(self._duplicate_active)
        self.delete_button.on_click(self._delete_active)
        for button in (
            self.copy_button,
            self.export_button,
            self.edit_button,
            self.rename_button,
            self.duplicate_button,
            self.delete_button,
        ):
            button.add_class("rn-context-action")
        self.delete_button.add_class("rn-context-danger")
        self.context_actions = widgets.HBox(
            [
                self.copy_button,
                self.export_button,
                self.edit_button,
                self.rename_button,
                self.duplicate_button,
                self.delete_button,
            ],
            layout=widgets.Layout(display="none"),
        )
        self.context_actions.add_class("rn-context-actions")
        self.tab_strip = widgets.HBox([self.tabs, self.add_button])
        self.tab_strip.add_class("rn-tab-strip")
        self.toolbar = widgets.HBox([self.tab_strip, self.context_actions])
        self.toolbar.add_class("rn-workspace-toolbar")
        self.output = widgets.Output()
        self.status = widgets.HTML('<div role="status" aria-live="polite"></div>')
        self.export_status = widgets.HTML(
            '<div class="rn-export-status" role="status" aria-live="polite"></div>'
        )
        self.copy_status = widgets.HTML(
            '<div class="rn-copy-status" role="status" aria-live="polite"></div>'
        )
        self.body = widgets.VBox([self.output])
        self.root = widgets.VBox(
            [
                self.css,
                self.toolbar,
                self.copy_status,
                self.export_status,
                self.status,
                self.body,
                self.notice,
                widgets.HBox([self.persistence, self.reapply_button]),
            ]
        )
        self.root.add_class("rn-viz-workspace")
        self.root.add_class("rn-theme-light")
        self._refresh_tabs()
        self._show_active()

    def _persistence_changed(self) -> None:
        state = self.manager.persistence_state
        messages = {
            "connecting": "Connecting to the VS Code metadata companion…",
            "pending": "Saving visualization metadata…",
            "session_only": self.manager.persistence_error
            or "Changes are available for this kernel session but are not persisted.",
            "conflict": "Visualization metadata changed in another view.",
        }
        message = messages.get(state, "")
        self.persistence.value = (
            f'<div class="rn-warning" role="status">⚠ {html.escape(message)}</div>'
            if message
            else ""
        )
        self.reapply_button.layout.display = "" if state == "conflict" else "none"

    def _reapply(self, _button: Any) -> None:
        self.manager.reapply()
        self._refresh_tabs()
        self._show_active()

    def _refresh_tabs(self) -> None:
        options = [("Table", "")] + [(item.name, item.id) for item in self.manager.list()]
        self._updating_tabs = True
        try:
            self.tabs.options = options
            active = self.manager.collection.active_id or ""
            self.tabs.value = active if any(value == active for _, value in options) else ""
        finally:
            self._updating_tabs = False
        self._update_context_actions()

    def _select_tab(self, change: dict[str, Any]) -> None:
        if self._updating_tabs or change["new"] is None:
            return
        self.manager.activate(change["new"] or None)
        self._show_active()

    def _show_active(self) -> None:
        from IPython.display import display

        self._update_context_actions()
        with self.output:
            self.output.clear_output(wait=True)
            if self.manager.collection.active_id is None:
                display(
                    self.widgets.HTML(
                        _table_html(self.result.dataframe, label="Query result table")
                    )
                )
                return
            spec = self.manager.get(self.manager.collection.active_id)
            try:
                copy_frame, prepared = _copy_frame(self.result.dataframe, spec)
                counts = {
                    "source": prepared.source_rows,
                    "filtered": prepared.filtered_rows,
                    "plotted": prepared.plotted_rows,
                }
                count_text = (
                    f"{counts.get('source', 0):,} source → "
                    f"{counts.get('filtered', 0):,} filtered → "
                    f"{counts.get('plotted', 0):,} plotted rows"
                )
                display(self.widgets.HTML(f'<div role="status">{count_text}</div>'))
                if spec.chart_type == "table":
                    display(
                        self.widgets.HTML(
                            _table_html(copy_frame, label=f"{spec.name} table")
                        )
                    )
                else:
                    display(self.widgets.HTML(_copy_payload(copy_frame)))
                    display(
                        build_figure(
                            self.result.dataframe, spec, self.theme, _prepared=prepared
                        )
                    )
            except VisualizationError as exc:
                display(
                    self.widgets.HTML(
                        '<div class="rn-error" role="alert">⚠ Needs attention: '
                        f"{html.escape(str(exc))}</div>"
                    )
                )

    def _next_name(self) -> str:
        existing = {item.name for item in self.manager.list()}
        index = 1
        while f"Visualization {index}" in existing:
            index += 1
        return f"Visualization {index}"

    def _open_add(self, _button: Any) -> None:
        self._open_editor(
            infer_visualization(self.result.dataframe, name=self._next_name()), creating=True
        )

    def _update_context_actions(self) -> None:
        active = self.manager.collection.active_id is not None
        self.context_actions.layout.display = "flex"
        self.copy_button.description = "Copy data" if active else "Copy table"
        self.copy_button.tooltip = (
            "Copy the prepared visualization data as TSV"
            if active
            else "Copy the complete bounded result as TSV"
        )
        for button in (
            self.export_button,
            self.edit_button,
            self.rename_button,
            self.duplicate_button,
            self.delete_button,
        ):
            button.layout.display = "" if active else "none"

    def _active_visualization(self) -> VisualizationSpec | None:
        active_id = self.manager.collection.active_id
        return self.manager.get(active_id) if active_id is not None else None

    def _edit_active(self, _button: Any) -> None:
        current = self._active_visualization()
        if current is not None:
            self._open_editor(current, creating=False)

    def _rename_active(self, _button: Any) -> None:
        current = self._active_visualization()
        if current is not None:
            self._rename(current)

    def _duplicate_active(self, _button: Any) -> None:
        current = self._active_visualization()
        if current is None:
            return
        self.manager.duplicate(current.id)
        self._refresh_tabs()
        self._show_active()

    def _delete_active(self, _button: Any) -> None:
        current = self._active_visualization()
        if current is not None:
            self._confirm_delete(current)

    def _rename(self, current: VisualizationSpec) -> None:
        name = self.widgets.Text(description="Name", value=current.name)
        name.add_class("rn-name-control")
        save = self.widgets.Button(description="Rename", button_style="primary")
        cancel = self.widgets.Button(description="Cancel")

        def commit(_button: Any) -> None:
            try:
                self.manager.rename(current.id, name.value)
            except VisualizationError as exc:
                self._error(exc)
                return
            self._refresh_tabs()
            self._show_active()
            self.body.children = (self.output,)

        save.on_click(commit)
        cancel.on_click(lambda _: setattr(self.body, "children", (self.output,)))
        panel = self.widgets.VBox(
            [
                self.widgets.HTML("<h4>Rename visualization</h4>"),
                name,
                self.widgets.HBox([cancel, save]),
            ]
        )
        panel.add_class("rn-dialog-panel")
        self.body.children = (panel,)

    def _confirm_delete(self, current: VisualizationSpec) -> None:
        delete = self.widgets.Button(description="Delete", button_style="danger")
        cancel = self.widgets.Button(description="Cancel")
        delete.on_click(lambda _: self._delete(current))
        cancel.on_click(lambda _: setattr(self.body, "children", (self.output,)))
        panel = self.widgets.VBox(
            [
                self.widgets.HTML(
                    f'<div role="alert">Delete “{html.escape(current.name)}”?</div>'
                ),
                self.widgets.HBox([cancel, delete]),
            ]
        )
        panel.add_class("rn-dialog-panel")
        self.body.children = (panel,)

    def _delete(self, current: VisualizationSpec) -> None:
        self.manager.delete(current.id)
        self._refresh_tabs()
        self.body.children = (self.output,)
        self._show_active()

    def _open_editor(self, spec: VisualizationSpec, *, creating: bool) -> None:
        self._draft = spec
        self._drafts = {spec.chart_type: spec}
        widgets = self.widgets
        self.name_control = widgets.Text(description="Name", value=spec.name)
        self.name_control.add_class("rn-name-control")
        self.type_control = widgets.Dropdown(
            description="Type",
            options=[(item.label, item.id) for item in list_visualization_definitions()],
            value=spec.chart_type,
        )
        self.type_control.observe(self._change_type, names="value")
        self.field_box = widgets.VBox()
        self.option_box = widgets.VBox()
        self.preview = widgets.Output()
        self.editor_error = widgets.HTML('<div role="status" aria-live="assertive"></div>')
        reset = widgets.Button(description="Reset")
        cancel = widgets.Button(description="Cancel")
        apply = widgets.Button(description="Apply", button_style="primary")
        self.apply_button = apply
        reset.on_click(lambda _: self._reset_editor())
        cancel.on_click(lambda _: self._cancel_editor())
        apply.on_click(lambda _: self._apply_editor(creating))
        self.name_control.observe(self._schedule_preview, names="value")
        self._build_controls(spec)
        panel = widgets.VBox(
            [
                self.name_control,
                self.type_control,
                self.field_box,
                self.option_box,
                self.editor_error,
                widgets.HBox([reset, cancel, apply]),
            ]
        )
        panel.add_class("rn-editor-panel")
        editor = widgets.HBox([self.preview, panel])
        editor.add_class("rn-editor")
        self.body.children = (editor,)
        self._render_preview()

    def _build_controls(self, spec: VisualizationSpec) -> None:
        columns = classify_columns(self.result.dataframe)
        definition = get_visualization_definition(spec.chart_type)
        existing: dict[str, list[FieldBinding]] = {}
        for binding in spec.fields:
            existing.setdefault(binding.role, []).append(binding)
        controls = []
        self.field_controls: dict[str, Any] = {}
        for role in definition.fields:
            compatible = [
                (f"{item.label} — {item.kind}", item.index)
                for item in columns
                if item.kind in role.dtypes
            ]
            options = compatible if role.minimum else [("—", None), *compatible]
            selected = existing.get(role.role, [])
            if role.maximum > 1:
                control = self.widgets.SelectMultiple(
                    description=role.label,
                    options=compatible,
                    value=tuple(item.column_index for item in selected),
                )
            else:
                control = self.widgets.Dropdown(
                    description=role.label,
                    options=options,
                    value=selected[0].column_index if selected else None,
                )
            control.observe(self._schedule_preview, names="value")
            self.field_controls[role.role] = control
            controls.append(control)
        self.field_box.children = tuple(controls)
        option_controls = []
        self.option_controls: dict[str, Any] = {}
        for item in definition.controls:
            value = spec.options.get(item.key, item.default)
            if item.kind == "checkbox":
                control = self.widgets.Checkbox(description=item.label, value=bool(value))
            elif item.kind == "integer":
                control = self.widgets.IntText(
                    description=item.label, value=int(cast(int, value or 0))
                )
            elif item.kind == "number":
                control = self.widgets.FloatText(
                    description=item.label, value=float(cast(float | int, value or 0))
                )
            elif item.kind == "select":
                control = self.widgets.Dropdown(
                    description=item.label, options=item.choices, value=value
                )
            else:
                control = self.widgets.Text(
                    description=item.label, value="" if value is None else str(value)
                )
            control.observe(self._schedule_preview, names="value")
            self.option_controls[item.key] = control
            option_controls.append(control)
        sections = self.widgets.Accordion(children=[self.widgets.VBox(option_controls)])
        sections.add_class("rn-options-section")
        sections.set_title(0, "Options")
        self.option_box.children = (sections,)

    def _collect_draft(self) -> VisualizationSpec:
        assert self._draft is not None
        columns = classify_columns(self.result.dataframe)
        previous = {(item.role, item.column_index): item for item in self._draft.fields}
        fields = []
        for role, control in self.field_controls.items():
            values = (
                control.value
                if isinstance(control.value, tuple)
                else (() if control.value is None else (control.value,))
            )
            for index in values:
                old = previous.get((role, index))
                fields.append(
                    old
                    or FieldBinding(
                        role,
                        columns[index].label,
                        index,
                        trace_type="bar"
                        if self.type_control.value == "combo" and role == "y"
                        else None,
                    )
                )
        options = {}
        for key, control in self.option_controls.items():
            value = control.value
            if isinstance(control, self.widgets.Text):
                value = value or None
            if isinstance(control, self.widgets.IntText) and value == 0 and key in ("limit",):
                value = None
            options[key] = value
        return replace(
            self._draft,
            name=self.name_control.value,
            chart_type=self.type_control.value,
            fields=tuple(fields),
            options=options,
        )

    def _schedule_preview(self, _change: Any = None) -> None:
        if self._pending:
            self._pending.cancel()
        self._generation += 1
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._render_preview()
        else:
            generation = self._generation
            self._pending = loop.call_later(0.3, lambda: self._render_preview(generation))

    def _render_preview(self, generation: int | None = None) -> None:
        from IPython.display import display

        if generation is not None and generation != self._generation:
            return
        try:
            draft = self._collect_draft()
            validate_visualization(self.result.dataframe, draft)
            figure = build_figure(self.result.dataframe, draft, self.theme)
        except (VisualizationError, ValueError) as exc:
            self.apply_button.disabled = True
            self._error(exc)
            return
        self._draft = draft
        self._drafts[draft.chart_type] = draft
        self.apply_button.disabled = False
        self.editor_error.value = '<div role="status" aria-live="assertive">Preview ready.</div>'
        with self.preview:
            self.preview.clear_output(wait=True)
            display(figure)

    def _change_type(self, change: dict[str, Any]) -> None:
        if self._draft:
            with suppress(Exception):
                self._drafts[change["old"]] = self._collect_draft()
        draft = self._drafts.get(change["new"])
        if draft is None:
            assert self._draft is not None
            inferred = infer_visualization(self.result.dataframe, name=self.name_control.value)
            draft = replace(
                inferred, id=self._draft.id, chart_type=change["new"], fields=(), options={}
            )
        self._draft = draft
        self._build_controls(draft)
        self._schedule_preview()

    def _reset_editor(self) -> None:
        assert self._draft is not None
        reset = infer_visualization(self.result.dataframe, name=self.name_control.value)
        if reset.chart_type != self.type_control.value:
            reset = replace(
                reset, id=self._draft.id, chart_type=self.type_control.value, fields=(), options={}
            )
        self._draft = reset
        self._build_controls(reset)
        self._schedule_preview()

    def _cancel_editor(self) -> None:
        self._pending.cancel() if self._pending else None
        self.body.children = (self.output,)
        self._show_active()

    def _apply_editor(self, creating: bool) -> None:
        try:
            draft = self._collect_draft()
            validate_visualization(self.result.dataframe, draft)
            self.manager.add(draft) if creating else self.manager.update(draft)
        except (VisualizationError, ValueError) as exc:
            self._error(exc)
            return
        self._refresh_tabs()
        self.body.children = (self.output,)
        self._show_active()

    def _error(self, exc: Exception) -> None:
        message = f"⚠ {html.escape(str(exc))}"
        if hasattr(self, "editor_error"):
            self.editor_error.value = f'<div class="rn-error" role="alert">{message}</div>'
        self.status.value = (
            f'<div class="rn-error" role="status" aria-live="assertive">{message}</div>'
        )

    def _theme_changed(self, theme: Any) -> None:
        self.theme = theme
        for class_name in ("rn-theme-light", "rn-theme-dark", "rn-theme-high-contrast"):
            self.root.remove_class(class_name)
        self.root.add_class(f"rn-theme-{theme.kind.replace('_', '-')}")
        if self._draft is not None and hasattr(self, "preview"):
            self._schedule_preview()
        else:
            self._show_active()


def build_workspace(result: Any) -> Any:
    return VisualizationWorkspace(result).root


__all__ = ["VisualizationWorkspace", "build_workspace"]
