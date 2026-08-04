# Visualization workspace

Install the optional Python dependencies:

```bash
uv pip install -e '.[viz]'
```

The visualization extra supports pandas 3.0.5 or newer within the pandas 3
release series and installs `nbformat` for Plotly notebook MIME rendering.
JupyterLab 4 metadata support and the VS Code companion VSIX are bundled with
the Python wheel. Install the latter into the active VS Code extension host:

```bash
redshift-notebooks vscode install
redshift-notebooks vscode status
```

Use `redshift-notebooks vscode path` for offline/manual installation. The
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
from redshift_notebooks.visualize import FieldBinding, FilterSpec, VisualizationSpec

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
`metadata.redshift_notebooks.visualizations` on the originating SQL cell. It
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
zoom, pan, reset, legend interaction, and secondary PNG download. Controls have keyboard
focus, programmatic labels, live validation status, and a responsive layout for
640-pixel notebook outputs and 200% browser zoom. Visualization name fields and
the expandable Options section use the active theme's input, surface, text,
border, selection, and focus colors.

## Visual design lab

Use the development lab to work on the real visualization controls without
building, installing, or reloading the VS Code extension:

```bash
scripts/run_visualization_lab.sh
```

The command starts Voilà on `http://localhost:8866`. Set
`REDSHIFT_NOTEBOOKS_LAB_PORT` when that port is already in use. Refreshing the
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
