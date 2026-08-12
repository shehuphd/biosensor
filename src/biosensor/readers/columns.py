"""Header-name and filename based column inference.

Used by the generic CSV reader, and exposed to the viewer so it can present
an inferred mapping for the user to confirm or correct before committing
(infer, then confirm).
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

# A trailing electrical unit token like "(mA)", "/mV", "(A)", "/V". The prefix
# group is empty for a base unit (volts, amps) and an SI prefix char otherwise.
# Micro is spelled with both the micro sign (µ) and Greek mu (μ) in the wild.
_UNIT_RE = re.compile(r"[/(]\s*(?P<prefix>[pnµμumkM]?)(?P<base>[VvAa])\s*\)?\s*$")


def column_unit(header: str) -> Optional[tuple[str, str]]:
    """Return ``(base, prefix)`` for a header's trailing electrical unit.

    ``base`` is ``"V"`` or ``"A"``; ``prefix`` is ``""`` for a base SI unit or
    the SI prefix character (``m``, ``µ``, ``u``, ``n``, ``p``, ``k``, ``M``).
    Returns ``None`` when the header carries no volt/amp unit token, in which
    case a base unit is assumed by the caller.
    """
    match = _UNIT_RE.search(header.strip())
    if not match:
        return None
    return match.group("base").upper(), match.group("prefix")


def _unit_backstop(
    headers: list[str], base: str, name_tokens: tuple[str, ...]
) -> Optional[str]:
    """Recognize a potential/current column by its unit when the name hints
    miss it, so a unit-bearing spelling like BioLogic's ``<I>/mA`` is caught
    (and can then be rejected for its non-base unit) instead of going
    unrecognized."""
    for header in headers:
        unit = column_unit(header)
        if unit and unit[0] == base:
            low = header.strip().lower()
            if any(token in low for token in name_tokens):
                return header
    return None


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
    potential = _best_match(headers, POTENTIAL_HINTS)
    current = _best_match(headers, CURRENT_HINTS)
    if potential is None:
        potential = _unit_backstop(headers, "V", ("e", "pot", "volt"))
    if current is None:
        current = _unit_backstop(headers, "A", ("i", "current", "amp"))
    return {
        "potential_v": potential,
        "current_a": current,
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
