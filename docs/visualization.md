# Notebook visualization

Install the optional dependencies:

```bash
uv pip install -e '.[viz]'
```

The visualization extra supports pandas 3, starting at pandas 3.0.5. pandas 2
is not supported.

With `visualization=True`, every `%%sql` SELECT result becomes a
`NotebookResult` with **Table** and **Visualization** tabs. Supported chart
types are table, bar, line, area, scatter, pie, histogram, and single value.

```python
result.dataframe
result.truncated
result.to_csv("<output-path>.csv")
```

## Bounded data

The default local limit is 10,000 rows. The integration fetches one additional
row to detect truncation, detaches the bounded DataFrame, and closes the result
cursor. All interactive filters and aggregations operate only on that local
DataFrame.

```python
session.register(max_rows=25_000)
```

Limits above 100,000 require `allow_large_results=True`. A larger local limit
does not reduce Redshift query cost; use `WHERE`, aggregation, and `LIMIT` in
SQL to bound warehouse work.

## Reproducible charts

```python
from redshift_notebooks.visualize import ChartSpec, FilterSpec

spec = ChartSpec(
    chart_type="bar",
    x="<category-column>",
    y=("<value-column>",),
    aggregation="sum",
    filters=(FilterSpec("<category-column>", "ne", "<excluded-value>"),),
)

result.visualize(spec)
spec.to_json()
spec.to_code("result")
```

Plotly's modebar provides client-side PNG download. The package does not mutate
notebook metadata; save the generated `ChartSpec` code when a visualization
must be reproducible.
