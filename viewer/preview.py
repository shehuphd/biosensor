"""Build a bounded, display-ready preview of a parsed dataframe.

Kept separate from app.py so it can be unit tested without Flask.
"""

from __future__ import annotations

import math

from biosensor.core import to_dataframe
from biosensor.schema import Measurement

DEFAULT_PREVIEW_ROWS = 50


def _format_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        # A missing optional field (cycle_number, scan_rate_v_s) is float64 NaN
        # in the frame, not None. Show it blank, the same as the exported CSV
        # and the "—" in the parse record, instead of the literal text "nan".
        if math.isnan(value):
            return ""
        return f"{value:.6g}"
    return str(value)


def _has_any_value(series) -> bool:
    """True when a column holds at least one displayable value.

    Optional schema fields (scan_rate_v_s, technique, sample_id, …) are often
    empty for a given file — all NaN or all blank. Those columns carry nothing
    to read on screen, so they're dropped from the preview.
    """
    for v in series:
        if v is None:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return True
    return False


def build_dataframe_preview(m: Measurement, limit: int = DEFAULT_PREVIEW_ROWS) -> dict:
    df = to_dataframe(m)
    total_rows = len(df)
    # Show only columns that carry a value, so an empty middle band of optional
    # fields doesn't force horizontal scrolling. The CSV export writes the full
    # schema; this trims the on-screen table only.
    all_columns = list(df.columns)
    columns = [c for c in all_columns if _has_any_value(df[c])] or all_columns
    head = df.head(limit)
    return {
        "columns": columns,
        "rows": [[_format_cell(v) for v in row]
                 for row in head[columns].itertuples(index=False)],
        "total_rows": total_rows,
        "shown_rows": len(head),
        "truncated": total_rows > limit,
        "hidden_columns": len(all_columns) - len(columns),
    }
