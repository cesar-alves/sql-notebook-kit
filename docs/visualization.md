# Visualization workspace

Install the optional Python dependencies:

```bash
uv pip install -e '.[viz]'
```

The visualization extra supports pandas 3.0.5 or newer within the pandas 3
release series and installs `nbformat` for Plotly notebook MIME rendering.
The base package installs `ipykernel` and `jupyter-client`, so the selected
Python environment includes the kernel runtime used by Jupyter and VS Code.
JupyterLab 4 metadata support and the VS Code companion VSIX are bundled with
the Python package. Published wheels and source distributions already contain
the compiled VSIX. Git and path installs build it automatically when it is
missing, so those source installs require Node.js and pnpm. To rebuild after
changing frontend sources, run:

```bash
pnpm install --frozen-lockfile
pnpm build:artifacts
```

Then install it into the active VS Code extension host:

```bash
sql-notebook-kit vscode install
sql-notebook-kit vscode status
```

Use `sql-notebook-kit vscode path` for offline/manual installation. The
installer supports `code`, `code-insiders`, and `codium`, plus `--cli` for a
compatible custom command. Run it in the matching remote terminal for SSH,
WSL, or dev-container windows, then reload the window. Microsoft Jupyter is a
required VS Code extension; browser-only `vscode.dev` is not supported.
VSCodium users must make the `ms-toolsai.jupyter` extension ID available in
their configured extension registry or install its compatible VSIX first.

With `visualization=True`, every managed `%sql` or `%%sql` result becomes a bounded
`NotebookResult`. Its first tab is the unmodified local table. Use **Add
visualization** through the adjacent **+** action to create named bar, line,
area, scatter, bubble, box, pie,
histogram, heatmap, combo, counter, or table visualizations.

Visualization tabs expose compact **Export PNG**, **Edit**, **Rename**,
**Duplicate**, and **Delete** buttons. Export opens the JupyterLab browser or VS
Code save picker. When a browser cannot choose a location, the companion copies
the image to the clipboard and finally falls back to a normal download. The
result row count appears below the active content, and table columns size
themselves from their returned values before sharing any remaining width.

The original result table exposes **Copy table** for its complete bounded local
result. Click and drag across cells, Shift-click from an anchor, or use the arrow
keys with Shift to select a rectangular range; Ctrl+C and Cmd+C copy exactly that
range, including headers only when header cells are selected. Named table
visualizations support the same interaction. Other visualization tabs expose
**Copy data**, which copies the filtered, bucketed, aggregated, sorted, and
limited data supplied to the chart. Histograms and other Plotly-derived marks
copy their prepared source values rather than reconstructed bins or pixels.
Clipboard data is plain TSV: nulls are empty and cells containing tabs, line
breaks, or quotes are quoted. Copying never reruns SQL and never includes rows
beyond the bounded local result.

```python
result.dataframe
result.truncated
result.visualizations.list()
result.visualize()
```

## Bounded data

The default local limit is 10,000 rows. The integration fetches one additional
row to detect truncation, detaches the bounded DataFrame, and closes the result
cursor. Filters, date buckets, aggregation, sorting, and limits operate only on
this detached frame and never rerun or rewrite SQL.

SQL `NUMERIC` and `DECIMAL` results remain Python `Decimal` values throughout
local filtering, aggregation, sorting, table display, and clipboard export.
They are not eagerly converted to `float64`. Numeric charts use a detached
Plotly-only projection because browsers represent plotted coordinates as
binary floating-point numbers; non-finite values and values that would overflow
or underflow that representation are rejected instead of silently becoming a
null or zero. The bounded result and prepared/copy data remain exact.

```python
session.register(max_rows=25_000)
```

Limits above 100,000 require `allow_large_results=True`. A larger local limit
does not reduce Redshift query cost; use SQL predicates, aggregation, and
`LIMIT` to bound warehouse work.

## Typed API

Specifications retain both a display label and positional column index, so
duplicate and non-string DataFrame columns remain unambiguous.

```python
from sql_notebook_kit.visualize import FieldBinding, FilterSpec, VisualizationSpec

spec = VisualizationSpec.create(
    "Revenue by region",
    "bar",
    fields=(
        FieldBinding("x", "region", 0),
        FieldBinding("y", "revenue", 1, aggregation="sum"),
    ),
    filters=(FilterSpec("region", 0, "not_equals", "Internal"),),
    options={"bar_mode": "grouped", "limit": 25},
)

result.visualizations.add(spec)
result.visualizations.rename(spec.id, "Regional revenue")
result.visualizations.duplicate(spec.id)
result.visualizations.export_json()
result.visualize(spec.id)
```

All public specification objects provide strict `to_json`/`from_json` methods.
Unknown fields, non-finite numbers, invalid UUIDs, and oversized collections
are rejected before rendering.

## Persistence capability

Applied state is stored under
`metadata.sql_notebook_kit.visualizations` on the originating SQL cell. It
contains specifications only—never result rows, Plotly figures, credentials,
drafts, or presentation theme state.

The workspace reports connecting and pending saves, then displays a
session-only warning when the companion is missing, incompatible, timed out,
or the notebook is read-only. A revision conflict reloads persisted state but
retains the local draft behind **Reapply changes**. Editing remains usable for
the current kernel session. In Python, inspect:

```python
result.visualizations.persistence_available
result.visualizations.dirty
result.visualizations.persistence_error
```

JupyterLab users can confirm the bundled extension with:

```bash
jupyter labextension list
```

VS Code users install the wheel-bundled VSIX and reload the window. Both
companions use protocol version 1 and compare-and-swap revisions so one view
cannot silently overwrite newer cell metadata.

JupyterLab registers a kernel comm target. VS Code receives requests through a
hidden custom MIME renderer, writes metadata with the public Notebook API, and
returns acknowledgements through the stable Jupyter extension kernel API after
the kernel becomes idle. Existing VS Code metadata is restored from the cell's
execute-request metadata. Neither frontend edits `.ipynb` files directly.

VS Code does not persist a live ipywidgets model across kernel sessions. When a
notebook is reopened, the companion replaces this package's stale widget output
with a rerun placeholder. Running the originating SQL cell rebuilds the widget
from fresh bounded data and restores the saved collection from cell metadata.

## Themes and accessibility

The workspace follows JupyterLab or VS Code light, dark, and high-contrast
themes without changing notebook metadata. Plotly modebars remain enabled for
zoom, pan, reset, legend interaction, and secondary PNG download. Controls have
keyboard focus, programmatic labels, live validation status, and a responsive
layout for 640-pixel notebook outputs and 200% browser zoom. Every editor label
and value—including Name, Type, field selectors, checkboxes, numeric inputs,
text inputs, and the expandable Options section—uses the active theme's input,
surface, text, border, selection, and focus colors. Editor rows fill the
configuration panel, with a consistent label column and controls that expand
into the remaining space.

Closing or applying the editor cancels queued previews and clears its transient
draft state. Late widget events, stale column selections, and theme changes
after the editor closes cannot rebuild a hidden preview or apply an invalid
draft.

The VS Code companion also themes the host-owned padding around a recognized SQL
Notebook Kit workspace. In both frontends, result-table grids remain visible
using the active theme's subtle border color, but generic Jupyter table frames
and unrelated ipywidget outputs are not restyled.

## Visual design lab

Use the development lab to work on the real visualization controls without
building, installing, or reloading the VS Code extension:

```bash
scripts/run_visualization_lab.sh
```

The command starts Voilà on `http://localhost:8866`. Set
`SQL_NOTEBOOK_KIT_LAB_PORT` when that port is already in use. Refreshing the
page starts a fresh kernel, so current Python and `workspace.css` changes are
loaded immediately.

The lab renders the production `VisualizationWorkspace` and Plotly figures. Its
development-only bridge simulates VS Code theme updates and deferred metadata
saves. The toolbar provides:

- fresh, saved, truncated, missing-value, empty, and invalid-binding scenarios;
- light, dark, and high-contrast themes;
- 1100-pixel and 640-pixel output frames plus 100% and 200% zoom;
- writable, connecting, and session-only persistence states; and
- save acknowledgement, conflict, and failure responses after a workspace edit.

For a manual visual pass, exercise add, preview, apply, export, edit, rename,
duplicate, delete, cancel, and reset. Repeat the editor flow at 640 pixels and 200% zoom,
then switch themes while the table, a chart, and the editor preview are visible.
Confirm keyboard focus remains visible, status messages are announced, and the
Plotly modebar and legend interactions still work.

This lab deliberately simulates the host boundary rather than the complete VS
Code shell. Existing renderer tests continue to cover VS Code message delivery
and token resolution; perform one extension smoke test before a release.
