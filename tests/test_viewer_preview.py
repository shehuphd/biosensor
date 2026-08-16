import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "viewer"))

from preview import _format_cell, build_dataframe_preview  # noqa: E402

from biosensor.readers.detect import detect_reader

from biosensor.core import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_preview_shape_and_truncation():
    result = load(FIXTURES / "chi_sample.txt")
    preview = build_dataframe_preview(result.measurement, limit=10)

    assert preview["total_rows"] == 41
    assert preview["shown_rows"] == 10
    assert preview["truncated"] is True
    assert "potential_v" in preview["columns"]
    assert len(preview["rows"]) == 10
    assert len(preview["rows"][0]) == len(preview["columns"])


def test_preview_no_truncation_when_within_limit():
    result = load(FIXTURES / "chi_sample.txt")
    preview = build_dataframe_preview(result.measurement, limit=1000)

    assert preview["truncated"] is False
    assert preview["shown_rows"] == 41


def test_empty_optional_columns_are_dropped_from_the_preview():
    # A bare two-column CSV has no cycle_number, scan_rate_v_s, etc.: those are
    # all NaN/blank in the frame, so the preview drops them rather than showing
    # empty columns that force horizontal scrolling. The CSV export keeps them.
    raw = b"Potential (V),Current (A)\n-0.3,0\n-0.29,1.6e-06\n-0.28,3.2e-06\n-0.27,4.7e-06\n-0.26,6.1e-06\n"
    m = detect_reader(raw, "livetest.csv").parse(raw, "livetest.csv")
    preview = build_dataframe_preview(m)
    assert "cycle_number" not in preview["columns"]
    assert "scan_rate_v_s" not in preview["columns"]
    # columns that carry values are kept
    assert "potential_v" in preview["columns"] and "current_a" in preview["columns"]
    assert preview["hidden_columns"] >= 2
    # a genuine numeric value is still shown
    pot_idx = preview["columns"].index("potential_v")
    assert preview["rows"][0][pot_idx] == "-0.3"
    # every kept column is non-empty in at least one row
    for idx in range(len(preview["columns"])):
        assert any(row[idx] != "" for row in preview["rows"])


def test_nan_and_none_cells_render_blank_not_the_text_nan():
    # The blank-not-"nan" guarantee for a partially-populated column: a NaN or
    # None cell shows empty, matching the exported CSV and the parse record.
    assert _format_cell(float("nan")) == ""
    assert _format_cell(None) == ""
    assert _format_cell(1.6e-06) == "1.6e-06"
