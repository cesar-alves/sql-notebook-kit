# Visualization workspace

Install the optional Python dependencies:

```bash
uv pip install -e '.[viz]'
```

The visualization extra supports pandas 3.0.5 or newer within the pandas 3
release series. JupyterLab 4 metadata support is bundled with the Python wheel.
VS Code additionally requires the `redshift-notebooks-vscode` companion VSIX.

With `visualization=True`, every `%%sql` result becomes a bounded
`NotebookResult`. Its first tab is the unmodified local table. Use **Add
visualization** to create named bar, line, area, scatter, bubble, box, pie,
histogram, heatmap, combo, counter, or table visualizations.

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

The workspace displays a session-only warning when the companion is missing,
incompatible, timed out, or the notebook is read-only. Editing remains usable
for the current kernel session. In Python, inspect:

```python
result.visualizations.persistence_available
result.visualizations.dirty
result.visualizations.persistence_error
```

JupyterLab users can confirm the bundled extension with:

```bash
jupyter labextension list
```

VS Code users install the separately built VSIX and reload the window. Both
companions use protocol version 1 and compare-and-swap revisions so one view
cannot silently overwrite newer cell metadata.

## Themes and accessibility

The workspace follows JupyterLab or VS Code light, dark, and high-contrast
themes without changing notebook metadata. Plotly modebars remain enabled for
zoom, pan, reset, legend interaction, and PNG download. Controls have keyboard
focus, programmatic labels, live validation status, and a responsive layout for
640-pixel notebook outputs and 200% browser zoom.
