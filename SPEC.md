# Visualization workspace specification

## Status and objective

This document specifies the next visualization system for `sql-notebook-kit`.
It replaces the current single-chart editor with a bounded, metadata-backed
workspace inspired by the authoring experience of Databricks notebooks. The
goal is not pixel-for-pixel parity. The goal is a predictable notebook workflow
in which a user can create multiple named visualizations, select a chart type,
and configure only the fields and options that are meaningful for that chart.

The system must remain safe for Redshift users. A visualization operates only
on the detached `NotebookResult.dataframe`; it must never rewrite, rerun, or
silently increase the cost of the source SQL query. When a result is truncated,
every visualization must say that its transformations exclude unfetched rows.

This is a clean replacement of the alpha `ChartSpec` interface. Compatibility
with serialized or constructed instances of the old type is not required.

### Success criteria

The feature is complete when:

1. A SQL result initially shows its bounded table and an **Add visualization**
   action.
2. A user can create, preview, apply, rename, duplicate, edit, reorder, and
   delete multiple named visualizations without writing Plotly code.
3. The editor changes its fields and controls when the visualization type
   changes and prevents invalid column/type combinations.
4. Applied configurations are stored in namespaced metadata on the originating
   SQL cell and are restored and revalidated after the cell is rerun.
5. The same operations are available through a typed Python API.
6. JupyterLab 4 and VS Code can persist the metadata through small frontend
   companions. Without a companion, the editor remains usable for the current
   kernel session and reports that changes are not persisted.
7. All filtering, date bucketing, aggregation, sorting, and limiting is
   deterministic, tested, and limited to the fetched DataFrame.
8. The table, editor, and every Plotly chart follow live JupyterLab/VS Code
   light, dark, and high-contrast theme changes without saving presentation
   state into the notebook.

## Existing system

The current implementation is concentrated in
`sql_notebook_kit/visualize.py` and `sql_notebook_kit/results.py`. It has
eight chart types, a flat frozen `ChartSpec`, one optional filter, one global
aggregation, and a fixed row of ipywidgets. Every widget is displayed for every
chart, whether or not the option applies. A result owns a single `chart` value,
and configurations persist only when users manually retain generated Python.

The useful contracts that must be retained are:

- visualization dependencies remain optional under the `viz` extra;
- `NotebookResult.dataframe` is detached and bounded;
- the source frame is not mutated by visualization transformations;
- a truncated result is visibly identified;
- a configuration is serializable independently of result data; and
- Plotly supplies zoom, legend interaction, and client-side PNG download.

## Scope

### Phase 1 visualization types

Phase 1 includes the following twelve integrated types:

| Type | Required field roles | Optional field roles | Type-specific options |
| --- | --- | --- | --- |
| Table | none; defaults to all columns | visible columns | column visibility and order |
| Bar | one X, one or more Y | group, symmetric or lower/upper error | orientation, grouped/stacked, normalize |
| Line | one X, one or more Y | group, symmetric or lower/upper error | line/marker display |
| Area | one X, one or more Y | group | stacked/overlay, normalize |
| Scatter | numeric X and numeric Y | group, symmetric or lower/upper error | marker opacity |
| Bubble | numeric X, numeric Y, numeric size | group | size coefficient, area/diameter sizing |
| Box | numeric value | category, group | orientation, show points |
| Pie | one category, one value | none | hole size, label content |
| Histogram | one numeric or datetime value | group | positive bin count, overlay/stack |
| Heatmap | one X dimension, one Y dimension, one numeric color measure | none | colorscale, reverse scale |
| Combo | one X, at least two Y series | none | trace type and left/right axis per series |
| Counter | one value column and row | target column and row | comparison and number format |

`X`, `Y`, `value`, and other names above are semantic roles. Renderers may map
them to different Plotly parameter names. Combo values must already be
query-prepared in Phase 1; combo does not expose editor aggregation.

Maps, pivot tables, funnels, Sankey diagrams, sunbursts, cohorts, and word
clouds are out of Phase 1. Their future addition must use the same registry and
must not require changes to the workspace controller or metadata protocol.
Dashboards, cross-cell filters, query rewriting, and warehouse-side
aggregation are out of scope.

### Databricks features used as product references

The UX should adopt these concepts from Databricks notebooks:

- the result table and visualizations occupy peer tabs;
- a visualization has create, edit, rename, duplicate, and delete operations;
- selecting a type determines its available general, axis, series, color, and
  label options;
- aggregation is selected alongside a measure;
- legend interaction temporarily hides or isolates series;
- preview and committed state are distinct; and
- filtering and bounded-row behavior are explicit.

The relevant references are:

- <https://docs.databricks.com/aws/en/visualizations/>
- <https://docs.databricks.com/aws/en/visualizations/visualization-types>
- <https://docs.databricks.com/aws/en/visualizations/charts>
- <https://docs.databricks.com/aws/en/visualizations/tables>

## User experience

### Result workspace

The first tab is always **Table** and shows the unmodified bounded DataFrame.
It is followed by one tab for each applied visualization and a final **+**
action. A fresh result has no automatically saved visualization.

The **+** action opens an unsaved editor. Its initial type and fields come from
the inference rules in this specification. Saving creates a tab named
`Visualization 1`, incrementing the suffix until the name is unique. Names are
trimmed, must contain at least one visible character, and are limited to 80
Unicode code points. Name matching for uniqueness is case-sensitive.

Each visualization tab exposes compact contextual buttons for **Edit**,
**Rename**, **Duplicate**, and **Delete**. These controls are hidden on the
Table tab. Duplicate makes a deep copy, assigns a new UUID, appends ` copy` to
the name with a numeric suffix if needed, inserts the copy immediately after
the source, and activates it. Delete requires confirmation and activates the
nearest preceding tab, or Table when no visualization remains. Dragging tabs
reorders visualizations and immediately commits the new order.

Below the active table or visualization, the workspace reports one of:

- `Using N local rows.`
- `Result truncated to N local rows; unfetched rows are excluded from all
  visualizations.`

Each chart additionally reports `source → filtered → plotted` row counts.
These counts describe local rows only.

### Editor

The editor keeps the chart preview visible beside a configuration panel. On
narrow notebook outputs the configuration panel moves below the preview. The
panel contains these tabs, omitting an empty tab for the selected chart:

1. **General** — visualization type and field roles.
2. **Axes** — scale, range, axis visibility, labels, sort, orientation, and
   datetime grain.
3. **Series** — series order, label, color, stacking, normalization, combo
   trace type, and combo axis.
4. **Style** — title, legend placement/order, palette, and missing-value policy.
5. **Labels** — data-label visibility and number, percent, date, and tooltip
   formatting.
6. **Filters** — an ordered collection of type-aware filter rows.

The panel footer contains **Reset**, **Cancel**, and **Apply**. Reset returns to
inferred defaults for the currently selected type. Cancel discards the draft
and returns to the applied chart or Table. Apply is enabled only after a
successful preview and commits the entire draft atomically.

Control changes schedule preview after 300 ms. A newer change cancels the
pending preview. Rendering must not block control feedback. If validation or
rendering fails, the last valid preview remains visible, the failing control is
marked, a concise error appears beside it, and an accessible status region
announces the failure. Raw exception text and tracebacks are never inserted as
HTML.

Changing chart type preserves title, filters, palette, and compatible field
bindings. It clears incompatible bindings and options, then displays a short
notice listing the cleared roles. Returning to an earlier type during the same
edit session restores that type's uncommitted draft. Only the selected type is
stored when Apply is pressed.

### Column selection and validation

The system classifies DataFrame columns as numeric, datetime, categorical,
boolean, or unsupported. Nullable pandas dtypes retain their logical class.
Column labels are normalized to strings for display but bindings also retain a
stable positional index so duplicate and non-string labels are unambiguous.

A field dropdown lists compatible columns first. Incompatible columns remain
visible but disabled with a reason such as `Requires numeric data`. A selected
column that becomes invalid after rerun remains displayed as missing or
incompatible until the user repairs it.

Multi-measure fields use an ordered list, not a multi-select box. Users add a
measure, choose its aggregation, rename it, and reorder or remove it. Series
controls are derived from this ordered list.

### Accessibility and visual behavior

All controls require programmatic labels, help text, keyboard access, visible
focus, and logical tab order. Status and validation changes use ARIA live
regions. Meaning must not be conveyed by color alone. The workspace must
inherit notebook typography and support JupyterLab and VS Code light and dark
themes. Controls must remain usable at 200% browser zoom and in a 640-pixel-wide
output area.

Plotly's standard modebar remains enabled for zoom, pan, reset, and PNG export.
Legend click and double-click retain Plotly's hide/isolate behavior and do not
modify the saved configuration.

### Theme architecture

Theme support is automatic. It is not a visualization setting and is never
stored in `VisualizationSpec` or notebook metadata. The same applied
visualization must follow the active frontend theme without becoming dirty.

Every workspace root has the CSS class `snk-viz-workspace` and exactly one of
`snk-theme-light`, `snk-theme-dark`, or `snk-theme-high-contrast`. All library CSS
is scoped beneath `snk-viz-workspace`; it must not style generic notebook,
`.widget-*`, or `.dataframe` elements outside that root. In normal light and
dark themes, the workspace root is unframed so it blends into the notebook
output; component borders remain available for tables, controls, warnings, and
other structural boundaries. Forced-colors mode retains an explicit root
boundary.

The frontend companion resolves host theme values into this stable semantic
token contract:

| Token | Use |
| --- | --- |
| `--snk-bg` | workspace and Plotly paper background |
| `--snk-surface` | table cells, panels, menus, and Plotly plot background |
| `--snk-surface-muted` | inactive tabs, alternating rows, and disabled controls |
| `--snk-surface-raised` | dropdown menus, tooltips, and dialogs |
| `--snk-text` | primary text and Plotly labels |
| `--snk-text-muted` | help text, placeholders, and secondary counts |
| `--snk-border` | table grid, dividers, inputs, and Plotly axes/grid |
| `--snk-accent` | active tab, primary action, selected option, and links |
| `--snk-accent-hover` | hovered primary action and link |
| `--snk-focus` | keyboard focus ring |
| `--snk-danger` | destructive action and validation error |
| `--snk-warning-bg` | bounded-result and persistence-warning background |
| `--snk-warning-text` | warning foreground |
| `--snk-selection-bg` | selected row, field, or menu item background |
| `--snk-input-bg` | input and select background |
| `--snk-shadow` | menu/dialog shadow; `none` in high-contrast mode |

JupyterLab maps these tokens from public `--jp-*` variables, preferring
`--jp-layout-color0/1/2`, `--jp-ui-font-color1/2`, `--jp-border-color1/2`,
`--jp-brand-color1/2`, `--jp-error-color1`, `--jp-warn-color3`, and
`--jp-ui-font-family`. The extension must not depend on `--jp-private-*`
variables. VS Code maps them from `--vscode-editor-background`,
`--vscode-editor-foreground`, `--vscode-descriptionForeground`,
`--vscode-panel-border`, `--vscode-input-background`,
`--vscode-list-activeSelectionBackground`, `--vscode-focusBorder`,
`--vscode-errorForeground`, and the editor font variables.

If a host token is absent, use these deterministic fallbacks:

| Semantic value | Light | Dark |
| --- | --- | --- |
| Background | `#ffffff` | `#1e1e1e` |
| Surface | `#ffffff` | `#252526` |
| Muted surface/input | `#f6f8fa` | `#313131` |
| Raised surface | `#ffffff` | `#2d2d30` |
| Text | `#1f2328` | `#f0f0f0` |
| Muted text | `#57606a` | `#c4c4c4` |
| Border | `#d0d7de` | `#5a5a5a` |
| Accent | `#0969da` | `#4daafc` |
| Accent hover/focus | `#0550ae` | `#75beff` |
| Danger | `#cf222e` | `#f48771` |
| Warning background | `#fff8c5` | `#3b2e00` |
| Warning text | `#4d2d00` | `#ffd866` |
| Selection background | `#ddf4ff` | `#063b49` |

Normal text must meet WCAG 2.2 AA contrast of 4.5:1 against its actual
background. Large text, component boundaries, chart marks, and focus indicators
must meet 3:1. A 2-pixel focus outline using `--snk-focus`, offset by 2 pixels,
is required and must not be removed for mouse interaction. Disabled controls
may use reduced emphasis but their labels must remain readable.

In forced-colors or VS Code high-contrast mode, semantic colors map to CSS
system colors: `Canvas`, `CanvasText`, `ButtonFace`, `ButtonText`, `GrayText`,
`Highlight`, `HighlightText`, and `Mark`. Components use a one-pixel solid
`CanvasText` boundary, selected/focused components use a two-pixel `Highlight`
boundary, shadows and gradients are disabled, and `forced-color-adjust` remains
`auto`. Error and warning states include an icon and text, never color alone.

### Theme detection and synchronization

The JupyterLab companion reads resolved public theme variables from the active
notebook document and subscribes to the application theme manager's change
signal. The VS Code companion uses the webview/body theme category and resolved
`--vscode-*` values and subscribes to color-theme changes. Both send a
non-persistent `theme_changed` bridge message containing:

```json
{
  "kind": "light | dark | high_contrast",
  "tokens": {
    "background": "#rrggbb",
    "surface": "#rrggbb",
    "surface_muted": "#rrggbb",
    "text": "#rrggbb",
    "text_muted": "#rrggbb",
    "border": "#rrggbb",
    "accent": "#rrggbb",
    "focus": "#rrggbb"
  }
}
```

Values must be resolved opaque `#rrggbb` colors, not CSS expressions. The
kernel validates the message and uses it only to construct Plotly templates.
CSS-based table and editor surfaces update immediately in the frontend. The
active Plotly chart is rerendered once after a 100 ms theme-change debounce;
inactive chart caches are invalidated and rerender when selected. Theme changes
must not change the collection revision, draft state, tab selection, filters,
zoom state of inactive charts, or notebook dirty state. The active chart's zoom
is restored by carrying its axis ranges through the theme-only rerender.

When the bridge is unavailable, CSS selects light/dark from
`prefers-color-scheme` and reacts to changes. The kernel uses the matching
built-in fallback palette. If the media query is unavailable, light is the
default. The session-only persistence warning remains readable in every mode.

### Editor and table styling contract

Native buttons, inputs, selects, checkboxes, tabs, menus, and dialogs must use
semantic tokens rather than literal foreground/background colors. Browser
default appearance may be retained only when it produces the tokenized
foreground, background, border, focus, disabled, hover, and selected states in
both supported frontends. Icons use `currentColor`; theme-specific bitmap icons
are forbidden.

The permanent result table and Table visualization use the same scoped table
component:

- table and cell backgrounds use `--snk-surface`, text uses `--snk-text`, and
  grid lines use `--snk-border`;
- columns use intrinsic content widths, distribute remaining workspace width
  through automatic table layout, and overflow horizontally when they cannot
  fit without clipping;
- the header is sticky and uses `--snk-surface-muted`, semibold text, and a
  bottom border at least two pixels wide;
- alternating rows use `--snk-surface-muted` at no more than 60% opacity over
  the surface; hover and keyboard-current rows use `--snk-selection-bg` plus a
  left accent indicator;
- numeric values align right; boolean, datetime, and text values align left;
- null values render as an em dash with muted text and accessible label `null`;
- horizontal and vertical scroll containers retain visible tokenized scrollbars
  where the host exposes scrollbar tokens;
- pinned/sticky cells receive an opaque surface and boundary so scrolled text
  cannot show through; and
- conditional formatting supplied by a future feature must pass the same
  contrast checks and must include a non-color cue.

The editor's preview surface uses `--snk-surface`, not a hard-coded white card.
Inactive tabs, disabled fields, dropdown options, tooltips, validation banners,
and destructive confirmations must each have explicit token-based foreground,
background, border, hover, focus, and selected states. Widget descriptions must
not rely on ipywidgets' fixed description width; labels wrap without clipping at
200% zoom. Visualization name inputs and the Options accordion header, body,
expanded state, and focus state use the same semantic tokens in light, dark,
and high-contrast themes.

### Plotly theme contract

The renderer constructs a new `go.layout.Template` for each theme context and
passes it explicitly to every Plotly Express or Graph Objects figure. It must
not mutate `plotly.io.templates.default`, which is process-global and could
affect unrelated notebook charts.

The template sets at least:

- `paper_bgcolor`, `plot_bgcolor`, and global `font.color/family`;
- title, subtitle, legend, annotation, and hover-label foreground/background;
- Cartesian axis line, tick, grid, and zero-line colors;
- polar, ternary, scene, geo, and color-axis backgrounds/boundaries where used;
- modebar background, icon, active-icon, and orientation styling;
- table-trace header/cell fill, font, and line colors; and
- counter number, delta, gauge, and title colors.

The default qualitative colorways are:

- Light: `#2563eb`, `#d97706`, `#059669`, `#dc2626`, `#7c3aed`,
  `#0891b2`, `#db2777`, `#65a30d`, `#9333ea`, `#475569`.
- Dark: `#60a5fa`, `#fbbf24`, `#34d399`, `#f87171`, `#a78bfa`,
  `#22d3ee`, `#f472b6`, `#a3e635`, `#c084fc`, `#94a3b8`.

Heatmaps default to a perceptually ordered sequential scale with visibly
distinct endpoints in the current theme. User-selected palettes and per-series
colors are preserved across theme changes, but all theme-owned surfaces and
text still change. UI controls do not expose Plotly paper/plot backgrounds;
code-only overrides may replace them and are then the caller's responsibility
for contrast.

High-contrast charts add redundant encodings: line series cycle dash styles,
scatter/bubble series cycle symbols, bar series cycle Plotly patterns, pie
slices use labels and contrasting boundaries, and heatmaps retain a visible
numeric colorbar. Data labels and hover text always use the resolved theme
foreground/background rather than assuming black or white.

## Configuration model

All public specification objects are frozen, slotted dataclasses with explicit
JSON conversion. JSON payloads use snake_case keys and reject unknown keys.
They contain JSON-compatible values only.

### Public types

```python
ChartType = Literal[
    "table", "bar", "line", "area", "scatter", "bubble", "box",
    "pie", "histogram", "heatmap", "combo", "counter",
]

Aggregation = Literal[
    "none", "sum", "average", "count", "count_distinct", "min", "max",
    "median", "standard_deviation", "variance",
]

@dataclass(frozen=True, slots=True)
class FieldBinding:
    role: str
    column: str
    column_index: int
    aggregation: Aggregation = "none"
    date_grain: Literal["none", "year", "quarter", "month", "week", "day",
                        "hour", "minute"] = "none"
    label: str | None = None
    axis: Literal["left", "right"] = "left"
    trace_type: Literal["bar", "line"] | None = None

@dataclass(frozen=True, slots=True)
class FilterSpec:
    column: str
    column_index: int
    operator: str
    value: JSONValue = None
    enabled: bool = True

@dataclass(frozen=True, slots=True)
class PlotlyOverrides:
    trace: dict[str, JSONValue] = field(default_factory=dict)
    layout: dict[str, JSONValue] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class VisualizationSpec:
    schema_version: Literal[1]
    id: str
    name: str
    chart_type: ChartType
    fields: tuple[FieldBinding, ...] = ()
    filters: tuple[FilterSpec, ...] = ()
    options: dict[str, JSONValue] = field(default_factory=dict)
    plotly_overrides: PlotlyOverrides | None = None

@dataclass(frozen=True, slots=True)
class VisualizationCollection:
    schema_version: Literal[1]
    revision: int
    active_id: str | None
    items: tuple[VisualizationSpec, ...]
```

`JSONValue` is the recursive union of `None`, boolean, integer, finite float,
string, lists of JSON values, and string-keyed mappings of JSON values. NaN,
infinity, callables, and arbitrary Python objects are rejected.

Bindings resolve by `column_index` first and verify that the string form of the
resolved label equals `column`. This supports duplicate and non-string labels
while detecting schema drift. UUIDs are lowercase UUIDv4 strings.

### NotebookResult API

`NotebookResult.visualizations` is a manager backed by an in-memory
`VisualizationCollection`. It provides:

```python
result.visualizations.list() -> tuple[VisualizationSpec, ...]
result.visualizations.get(id_or_name: str) -> VisualizationSpec
result.visualizations.add(spec: VisualizationSpec, *, persist: bool = True) -> VisualizationSpec
result.visualizations.update(spec: VisualizationSpec, *, persist: bool = True) -> VisualizationSpec
result.visualizations.rename(id_or_name: str, name: str, *, persist: bool = True) -> VisualizationSpec
result.visualizations.duplicate(id_or_name: str, *, persist: bool = True) -> VisualizationSpec
result.visualizations.delete(id_or_name: str, *, persist: bool = True) -> None
result.visualizations.activate(id_or_name: str | None, *, persist: bool = True) -> None
result.visualizations.export_json() -> str
result.visualizations.import_json(value: str, *, replace: bool = False,
                                  persist: bool = True) -> tuple[VisualizationSpec, ...]
result.visualize(id_or_name: str | None = None) -> Any
```

Names that match multiple items raise an ambiguity error; UUID lookup is
preferred. `replace=False` imports items with new IDs and de-duplicates names.
`replace=True` atomically replaces the collection after the complete payload
validates. A persistence failure leaves the in-memory operation applied but
marks the collection dirty and reports the fallback state.

The old `NotebookResult.chart` attribute is removed. The package exports the
new public dataclasses from `sql_notebook_kit.visualize`, not from the
top-level package, preserving the optional dependency boundary.

### Discovery API

The library exposes read-only discovery:

```python
list_visualization_definitions() -> tuple[VisualizationDefinition, ...]
get_visualization_definition(chart_type: ChartType) -> VisualizationDefinition
```

Returned definitions contain only serializable descriptive fields. Renderer
callables and internal predicates are not public. Third-party chart
registration is deliberately unsupported in Phase 1.

## Visualization registry

The registry is the sole source of truth for UI controls and render behavior.
No chart-type `if` chain may be duplicated in the widget layer.

Each internal definition declares:

- stable ID, display label, description, and renderer function;
- inference priority and default builder;
- ordered field-role definitions with cardinality and dtype rules;
- allowed per-field aggregations and date grains;
- ordered control definitions grouped into editor sections; and
- transformation and renderer capabilities.

Each control definition declares a stable option key, label, help text, editor
section, widget kind, default, choices or numeric bounds, applicability
predicate, validator, and one translation target:

- `transform` for data preparation;
- `express` for a Plotly Express keyword;
- `trace` for `Figure.update_traces`;
- `layout` for `Figure.update_layout`; or
- `renderer` for a chart-specific renderer argument.

The exposed editor is curated. It must not enumerate Plotly's private
`_valid_props`, constructor signatures, or generated validators to create
controls. Plotly Express creates ordinary charts; Graph Objects implements
table, counter, combo, and post-render updates. Code-only overrides are applied
last using Plotly's public validation behavior. Invalid overrides produce a
path-specific `VisualizationConfigError`.

Renderers receive an immutable internal `ThemeContext` in addition to the
prepared data and specification. `ThemeContext` contains the validated theme
kind, resolved semantic colors, font family, and selected automatic colorway.
Theme context is mandatory for workspace rendering and defaults to the light
fallback only for direct headless Python calls.

## Transform semantics

`prepare_data(frame, spec)` returns a new prepared frame plus row-count and
series metadata. It never mutates `frame`. Operations execute in this order:

1. Resolve and validate every bound/filter column.
2. Copy the required columns from the bounded source.
3. Apply enabled filters in their displayed order using AND semantics.
4. Bucket datetime bindings by their configured date grain.
5. Apply the selected missing-value policy.
6. Group and aggregate supported measures.
7. Apply categorical or value sorting.
8. Apply the positive plotted-row/category limit.
9. Reshape to the renderer's long or matrix form.

Filtering operators are type-aware:

| Column class | Operators |
| --- | --- |
| All | equals, not equals, is null, is not null, in, not in |
| Numeric/datetime | greater than, greater or equal, less than, less or equal, between |
| Categorical | contains, not contains, starts with, ends with |
| Boolean | equals, not equals, is null, is not null |

String matching is literal and case-sensitive by default; an explicit
case-insensitive toggle is stored in the filter value object. It is never
interpreted as a regular expression. `between` is inclusive. `in` and `not in`
require a non-empty array. Date/time input is parsed against the selected
column's timezone and rejects ambiguous or nonexistent local times.

The missing-value policy is `hide` or `zero`; `zero` is offered only where the
affected value binding is numeric. Group keys retain null groups when `hide`
does not apply to that role.

Aggregation is stored on each measure. Numeric measures allow all aggregation
values. Categorical measures allow only count and count-distinct. `count`
counts source rows and does not require a value column; its generated series
label defaults to `Count`. Standard deviation uses sample standard deviation.
Variance uses sample variance. Empty aggregates render an empty-state message,
not a fabricated zero.

Sorting can target the X/category binding or one rendered measure and can be
ascending or descending. A limit is applied after sorting and aggregation.
Histogram bins and box quartiles are computed by Plotly from the filtered local
values and therefore bypass ordinary group aggregation.

## Inference

Inference runs only when opening Add or Reset and never overwrites an applied
specification:

1. Datetime plus numeric columns produce line with the first datetime as X and
   first numeric as Y.
2. Categorical plus numeric columns produce bar with the first categorical as
   X and first numeric as Y.
3. Two or more numeric columns produce scatter with the first two numerics.
4. One numeric column produces histogram.
5. All other non-empty frames produce table.
6. Empty or zero-column frames produce table with an empty-state message.

Column order breaks ties. Inferred aggregation is `none`; the library does not
guess whether query output is already aggregated.

## Metadata persistence

### Stored representation

The originating SQL code cell owns this namespaced metadata:

```json
{
  "sql_notebook_kit": {
    "visualizations": {
      "schema_version": 1,
      "revision": 3,
      "active_id": "<uuid-or-null>",
      "items": ["<serialized VisualizationSpec objects>"]
    }
  }
}
```

Only applied state is stored. Drafts, DataFrame values, query results, Plotly
figure JSON, errors, credentials, and widget state are forbidden. Unknown
future schema versions are preserved by the frontend but not loaded by the
kernel; the workspace shows an upgrade-required message.

### Frontend bridge

Cell metadata is controlled by notebook frontends, so persistence requires a
versioned bridge. JupyterLab uses the
`sql_notebook_kit.visualizations.v1` comm target. VS Code uses the companion's
custom MIME renderer for requests and the stable Microsoft Jupyter kernel API
for deferred responses after the kernel becomes idle. VS Code restores the
collection directly from execute-request cell metadata. Messages are JSON and
include `protocol_version`, `request_id`, `session_id`, `cell_id`, and the
operation payload.

Supported operations are:

- `capabilities` / `capabilities_result`;
- `load` / `load_result`;
- `save` / `save_result`; and
- `theme_changed`; and
- `error`.

The frontend associates the request with its notebook cell ID. In VS Code this
is `NotebookCell.document.uri`, matching the `cellId` sent to the kernel.
`load` returns absent metadata as an empty revision-zero collection. `save`
includes `expected_revision` and the entire next collection. The frontend
performs compare-and-swap, writes the namespaced cell metadata using its public
Notebook API, marks the document dirty, and returns the new revision. It must
never write the `.ipynb` file directly.

On a revision conflict the frontend returns the current payload. The kernel
keeps the user's draft, refreshes applied state, and offers **Reapply changes**;
it never silently overwrites the newer metadata.

JupyterLab support and the prebuilt VS Code VSIX are bundled into the Python
wheel. The VS Code companion uses the public Notebook API and is installed with
`sql-notebook-kit vscode install`. The two implementations share
protocol fixtures. A missing, timed-out, read-only, or incompatible bridge
switches to session-only mode without disabling chart creation.

### Restore after execution

After a SQL cell reruns, the result loads the cell's collection and validates
every specification against the new DataFrame. Valid charts render on demand.
A chart with missing columns, moved duplicate columns, incompatible dtypes, or
invalid options remains as a tab labeled **Needs attention**. Opening it takes
the user to the first invalid control. One invalid chart must not prevent other
charts or the table from rendering.

If a cell is copied, its metadata and visualization IDs are copied with it;
they are independent because persistence is cell-scoped. Clearing outputs does
not clear configurations. Deleting the cell deletes them naturally. Renaming,
moving, or reordering a cell preserves them through the notebook's stable cell
ID.

## Errors and security

Add `VisualizationError`, `VisualizationConfigError`,
`VisualizationRenderError`, and `VisualizationPersistenceError` under the
package's existing error hierarchy. Errors exposed in widgets contain safe,
concise messages and structured field paths. Detailed exceptions may be
chained for Python callers but must not expose DataFrame values or connection
information.

All user labels, column names, filter summaries, and error messages are escaped
before entering HTML widgets. Plotly text configuration accepts plain text and
the documented safe formatting subset only. Link, image, raw HTML, custom
JavaScript, and arbitrary hover-template execution are out of scope.

Import validates payload size, nesting depth, item count, UUIDs, and every
option before allocation or rendering. Initial limits are 50 visualizations
per result, 50 filters per visualization, 50 field bindings per visualization,
and 256 KiB for the serialized collection. Exceeding a limit fails atomically.

## Packaging and compatibility

The Python editor continues to use ipywidgets 8 and supports JupyterLab and VS
Code notebook widget rendering. Plotly support remains within the declared
`>=5.24,<7` range; CI must test the minimum supported release and the newest
compatible release. The registry targets public Plotly Express arguments and
`update_traces`/`update_layout`, not private schema attributes.

The JupyterLab prebuilt assets are included in wheels and source distributions.
The VS Code companion is versioned independently but declares its compatible
protocol range. Documentation must show how to confirm persistence capability
and must distinguish Python visualization installation from VS Code extension
installation.

## Testing and acceptance

### Python unit tests

- JSON round-trip and rejection tests for every public specification type.
- Registry completeness and uniqueness tests for all twelve chart types.
- Field cardinality, dtype, aggregation, and option validation per type.
- Assertions on Plotly trace types and material layout values rather than full,
  version-sensitive figure snapshots.
- Transform-order tests covering filters, datetime grain, null handling,
  aggregation, sorting, limiting, and reshaping.
- Nullable strings/integers/booleans, timezone-aware datetimes, duplicate and
  non-string labels, empty frames, all-null fields, NaN/infinity, and source
  copy-on-write behavior.
- Filter semantics, including literal special characters and invalid typed
  values.
- Collection CRUD, naming, ordering, atomic import, revision state, and
  persistence failures.
- Light, dark, and high-contrast `ThemeContext` validation, fallback selection,
  and Plotly template construction without mutation of
  `plotly.io.templates.default`.
- Material theme assertions for every renderer: paper/plot backgrounds, text,
  axes, legend, hover labels, table trace, counter trace, qualitative palette,
  and high-contrast dash/symbol/pattern redundancy.

### Controller and widget tests

- Fresh result, Add, Apply, Cancel, Reset, Edit, Rename, Duplicate, Reorder,
  Delete, and activation flows.
- Conditional control visibility for every chart definition.
- Type switching preserves compatible fields, reports cleared fields, and
  restores per-type draft state.
- Debounce coalesces rapid changes and stale render completions cannot replace
  a newer preview.
- Invalid drafts retain the last valid preview and disable Apply.
- Missing bridge fallback and dirty-state recovery.
- A theme change preserves the draft, applied spec, collection revision, active
  tab, filters, and active Cartesian axis ranges while causing exactly one
  debounced active-chart rerender.

### Frontend and notebook tests

- Shared protocol fixtures pass in JupyterLab and VS Code implementations.
- Load/save round-trip, compare-and-swap conflict, read-only notebook,
  incompatible protocol, absent metadata, and malformed metadata.
- A saved `.ipynb` contains the exact namespaced configuration and no source
  data or figure payload.
- Reopening and rerunning restores valid charts and flags schema drift.
- Clearing output preserves cell metadata; deleting the cell removes it.
- End-to-end tests cover keyboard-only creation and editing in light, dark, and
  high-contrast themes at normal and narrow widths.
- Theme-switch tests exercise JupyterLab and VS Code without rerunning the cell,
  verify the workspace root theme class and resolved tokens, and confirm that
  theme changes do not modify cell metadata or dirty an otherwise clean
  notebook.
- Automated axe checks report no serious or critical violations. Contrast tests
  sample table/editor foreground-background pairs and Plotly text/surfaces,
  enforcing 4.5:1 for normal text and 3:1 for large text, boundaries, focus,
  and chart marks.
- Screenshot baselines cover the result table, editor, validation state,
  warning banner, representative Cartesian chart, heatmap, table trace, and
  counter in all three theme kinds. Baselines are frontend-specific and use
  fixed fonts, viewport, data, and device scale.
- Forced-colors tests confirm visible focus, selected state, disabled state,
  table boundaries, error/warning icons, and redundant chart encodings with
  gradients and shadows disabled.

### Performance gates

Using a documented reference machine and the default 10,000-row bound:

- widget interaction updates visible control state within 100 ms;
- preview work starts once, 300 ms after the final rapid change;
- representative bar, line, scatter, histogram, and heatmap previews complete
  within one second; and
- switching to Table does not recompute chart transformations.

Performance failures must report the fixture, row count, chart type, and timing
rather than silently relaxing the bound.

### Repository gates

The implementation is accepted only when these pass:

```bash
uv run pytest
uv run ruff check .
uv run mypy sql_notebook_kit
uv run --group docs mkdocs build --strict
uv build
```

Frontend packages additionally require type checking, unit tests, production
builds, and their JupyterLab/VS Code integration suites.

## Delivery sequence

1. Introduce the public specifications, validation errors, registry, inference,
   transform pipeline, twelve renderers, and Python tests.
2. Replace the fixed builder with the workspace controller and conditional
   ipywidgets editor; add collection CRUD and accessibility behavior.
3. Implement the comm protocol and bundled JupyterLab metadata bridge.
4. Implement and publish the VS Code companion against the same protocol
   fixtures.
5. Add notebook round-trip and frontend end-to-end coverage, migration notes,
   user documentation, and examples.

Each step must leave the bounded-result and optional-dependency test suites
green. The user-facing feature is not considered complete until both metadata
companions and the documented session-only fallback are available.

## External implementation references

- Plotly Express API: <https://plotly.com/python-api-reference/plotly.express.html>
- Plotly Graph Objects: <https://plotly.com/python/graph-objects/>
- Plotly figure updates: <https://plotly.com/python/creating-and-updating-figures/>
- Plotly FigureWidget dependency note: <https://plotly.com/python/figurewidget/>
- ipywidgets reference: <https://ipywidgets.readthedocs.io/en/latest/reference/ipywidgets.html>
- Jupyter notebook format: <https://nbformat.readthedocs.io/en/v5.10.2/>
- JupyterLab notebook extension API:
  <https://jupyterlab.readthedocs.io/en/stable/extension/notebook.html>
- VS Code Notebook API:
  <https://code.visualstudio.com/api/extension-guides/notebook>
- JupyterLab CSS and public theme variables:
  <https://jupyterlab.readthedocs.io/en/stable/developer/css.html>
- VS Code webview theme classes and variables:
  <https://code.visualstudio.com/api/extension-guides/webview>
- Plotly templates: <https://plotly.com/python/templates/>
