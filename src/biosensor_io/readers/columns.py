"""Header-name and filename based column inference.

Used by the generic CSV reader, and exposed to the viewer so it can present
an inferred mapping for the user to confirm or correct before committing,
per the PRD's "infer then confirm" pattern.
"""

from __future__ import annotations

import re
from typing import Optional

POTENTIAL_HINTS = ["potential", "voltage", "e/v", "e (v)", "ewe", "e_v", "volt"]
CURRENT_HINTS = ["current", "i/a", "i (a)", "amp", "i_a"]
SAMPLE_ID_HINTS = ["sample_id", "sample id", "sample", "specimen"]
CONCENTRATION_HINTS = ["concentration", "conc", "analyte_concentration"]
UNIT_HINTS = ["unit", "concentration_unit"]

_CONC_FILENAME_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>pM|nM|uM|µM|mM|M|ng/mL|ug/mL|pg/mL)",
    re.IGNORECASE,
)


def _best_match(headers: list[str], hints: list[str]) -> Optional[str]:
    lowered = {h: h.strip().lower() for h in headers}
    for header, low in lowered.items():
        for hint in hints:
            if low == hint:
                return header
    for header, low in lowered.items():
        for hint in hints:
            if hint in low:
                return header
    return None


def infer_column_mapping(headers: list[str]) -> dict[str, Optional[str]]:
    """Best-effort mapping from schema fields to source column names."""
    return {
        "potential_v": _best_match(headers, POTENTIAL_HINTS),
        "current_a": _best_match(headers, CURRENT_HINTS),
        "sample_id": _best_match(headers, SAMPLE_ID_HINTS),
        "analyte_concentration": _best_match(headers, CONCENTRATION_HINTS),
        "concentration_unit": _best_match(headers, UNIT_HINTS),
    }


def infer_from_filename(filename: str) -> dict[str, Optional[str]]:
    """Best-effort sample_id / concentration guess from filename conventions.

    Looks for a trailing concentration+unit token (e.g. "sample3_10nM.csv")
    and otherwise treats the filename stem as the sample id.
    """
    stem = filename.rsplit(".", 1)[0]
    result: dict[str, Optional[str]] = {
        "sample_id": stem,
        "analyte_concentration": None,
        "concentration_unit": None,
    }
    match = _CONC_FILENAME_RE.search(filename)
    if match:
        try:
            result["analyte_concentration"] = float(match.group("value"))
        except ValueError:
            pass
        result["concentration_unit"] = match.group("unit")
    return result
