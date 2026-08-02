import pandas as pd
import pytest

from redshift_notebooks.results import NotebookResult
from redshift_notebooks.visualize import ChartSpec, FilterSpec, build_figure, prepare_data


def test_chart_spec_infers_categorical_bar_chart():
    frame = pd.DataFrame({"category": ["a", "b"], "amount": [1, 2]})
    assert isinstance(frame["category"].dtype, pd.StringDtype)
    spec = ChartSpec.infer(frame)
    assert spec.chart_type == "bar"
    assert spec.x == "category"
    assert spec.y == ("amount",)


def test_chart_spec_infers_timezone_aware_datetime_line_chart():
    frame = pd.DataFrame(
        {
            "occurred_at": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
            "amount": [1, 2],
        }
    )

    spec = ChartSpec.infer(frame)

    assert spec.chart_type == "line"
    assert spec.x == "occurred_at"
    assert spec.y == ("amount",)


def test_chart_spec_json_round_trip_and_code_generation():
    spec = ChartSpec(
        chart_type="bar",
        x="category",
        y=("amount",),
        filters=(FilterSpec("category", "in", ["a", "b"]),),
    )
    restored = ChartSpec.from_json(spec.to_json())
    assert restored == spec
    assert "ChartSpec.from_json" in spec.to_code()


def test_prepare_data_filters_aggregates_sorts_and_limits():
    frame = pd.DataFrame({"category": ["a", "a", "b", "c"], "amount": [1, 2, 10, 100]})
    spec = ChartSpec(
        chart_type="bar",
        x="category",
        y=("amount",),
        aggregation="sum",
        filters=(FilterSpec("category", "ne", "c"),),
        sort_by="amount",
        sort_descending=True,
        limit=1,
    )
    result = prepare_data(frame, spec)
    assert result.to_dict("records") == [{"category": "b", "amount": 10}]


def test_prepare_data_handles_nullable_strings_values_and_groups():
    frame = pd.DataFrame(
        {
            "category": ["alpha", None, "beta", "alphabet"],
            "amount": pd.array([1, 2, None, 4], dtype="Int64"),
        }
    )
    filtered = prepare_data(
        frame,
        ChartSpec(filters=(FilterSpec("category", "contains", "alpha"),)),
    )
    grouped = prepare_data(
        frame,
        ChartSpec(x="category", aggregation="count"),
    )

    assert filtered["category"].tolist() == ["alpha", "alphabet"]
    assert grouped["count"].sum() == 4
    assert grouped["category"].isna().sum() == 1


def test_prepare_data_does_not_mutate_source_under_copy_on_write():
    frame = pd.DataFrame({"category": ["a", "b"], "amount": [2, 1]})
    original = frame.copy()

    prepared = prepare_data(
        frame,
        ChartSpec(sort_by="amount", sort_descending=True, limit=1),
    )
    prepared.loc[prepared.index[0], "amount"] = 99

    pd.testing.assert_frame_equal(frame, original)


def test_notebook_result_exports_and_renders_pandas_3_data():
    frame = pd.DataFrame({"category": ["alpha", None], "amount": [1, 2]})
    result = NotebookResult(dataframe=frame, raw=None)

    assert result.to_csv() == "category,amount\nalpha,1\n,2\n"
    html = result._repr_html_()
    assert "alpha" in html
    assert "<table" in html


@pytest.mark.parametrize(
    "chart_type",
    ["table", "bar", "line", "area", "scatter", "pie", "histogram", "value"],
)
def test_build_figure_supports_every_documented_chart_type(chart_type):
    frame = pd.DataFrame({"category": ["a", "b"], "amount": [1, 2]})
    spec = ChartSpec(chart_type=chart_type, x="category", y=("amount",))
    assert build_figure(frame, spec) is not None


def test_prepare_data_rejects_unknown_columns_and_bad_limits():
    frame = pd.DataFrame({"amount": [1]})
    with pytest.raises(ValueError, match="does not exist"):
        prepare_data(frame, ChartSpec(filters=(FilterSpec("missing", "eq", 1),)))
    with pytest.raises(ValueError, match="positive"):
        prepare_data(frame, ChartSpec(limit=0))
