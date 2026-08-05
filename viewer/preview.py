"""Build a bounded, display-ready preview of a parsed dataframe.

Kept separate from app.py so it can be unit tested without Flask.
"""

from __future__ import annotations

from biosensor_io.core import to_dataframe
from biosensor_io.schema import Measurement

DEFAULT_PREVIEW_ROWS = 50


def _format_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def build_dataframe_preview(m: Measurement, limit: int = DEFAULT_PREVIEW_ROWS) -> dict:
    df = to_dataframe(m)
    total_rows = len(df)
    head = df.head(limit)
    return {
        "columns": list(head.columns),
        "rows": [[_format_cell(v) for v in row] for row in head.itertuples(index=False)],
        "total_rows": total_rows,
        "shown_rows": len(head),
        "truncated": total_rows > limit,
    }
