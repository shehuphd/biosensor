import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "viewer"))

from preview import build_dataframe_preview  # noqa: E402

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


def test_missing_optional_columns_render_blank_not_nan():
    # A bare two-column CSV has no cycle_number or scan_rate_v_s: those are
    # float64 NaN in the frame. The preview must show them blank, matching the
    # exported CSV and the parse record, never the literal text "nan".
    raw = b"Potential (V),Current (A)\n-0.3,0\n-0.29,1.6e-06\n-0.28,3.2e-06\n-0.27,4.7e-06\n-0.26,6.1e-06\n"
    m = detect_reader(raw, "livetest.csv").parse(raw, "livetest.csv")
    preview = build_dataframe_preview(m)
    for col in ("cycle_number", "scan_rate_v_s"):
        idx = preview["columns"].index(col)
        cells = {row[idx] for row in preview["rows"]}
        assert cells == {""}, f"{col} should be blank, got {cells}"
    # a genuine numeric value is still shown
    pot_idx = preview["columns"].index("potential_v")
    assert preview["rows"][0][pot_idx] == "-0.3"
