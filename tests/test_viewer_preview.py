import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "viewer"))

from preview import build_dataframe_preview  # noqa: E402

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
