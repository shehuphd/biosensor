"""Sanity-check heuristics for parsed measurements.

v1 heuristic: a simple curve-shape check
(monotonicity, peak presence, expected symmetry) rather than anything
trained. This is a first pass meant to catch silent parse failures (wrong
columns, garbage values, truncated data), not to judge assay quality.
Manual override is always available; this only sets an initial status.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from itertools import chain

from biosensor.schema import Measurement, QCRecord

HEURISTIC_VERSION = "0.1"

MIN_POINTS = 5
MAX_PLAUSIBLE_POTENTIAL_V = 5.0


def _sign_changes(values: list[float]) -> int:
    changes = 0
    prev_sign = 0
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        if diff == 0:
            continue
        sign = 1 if diff > 0 else -1
        if prev_sign != 0 and sign != prev_sign:
            changes += 1
        prev_sign = sign
    return changes


def sanity_check(measurement: Measurement) -> QCRecord:
    filename = measurement.source_filename
    now = datetime.now(timezone.utc)

    reasons: list[str] = []

    if measurement.n_points < MIN_POINTS:
        return QCRecord(
            filename=filename,
            parse_timestamp=now,
            sanity_status="failed",
            sanity_reason=f"only {measurement.n_points} data points parsed",
            heuristic_version=HEURISTIC_VERSION,
        )

    non_finite = any(
        not math.isfinite(v)
        for v in chain(measurement.potential_v, measurement.current_a)
    )
    if non_finite:
        return QCRecord(
            filename=filename,
            parse_timestamp=now,
            sanity_status="failed",
            sanity_reason="NaN or infinite values in parsed data",
            heuristic_version=HEURISTIC_VERSION,
        )

    pot_range = max(measurement.potential_v) - min(measurement.potential_v)
    cur_range = max(measurement.current_a) - min(measurement.current_a)

    if pot_range == 0:
        return QCRecord(
            filename=filename,
            parse_timestamp=now,
            sanity_status="failed",
            sanity_reason="potential column is constant, likely wrong column mapping",
            heuristic_version=HEURISTIC_VERSION,
        )
    if cur_range == 0:
        return QCRecord(
            filename=filename,
            parse_timestamp=now,
            sanity_status="failed",
            sanity_reason="current column is constant (flat line), likely wrong column mapping",
            heuristic_version=HEURISTIC_VERSION,
        )
    if pot_range > MAX_PLAUSIBLE_POTENTIAL_V:
        reasons.append(
            f"potential range ({pot_range:.2f} V) is unusually wide for an "
            f"electrochemical sweep"
        )

    sweep_changes = _sign_changes(measurement.potential_v)
    if sweep_changes == 0 and measurement.technique and "linear" not in measurement.technique.lower():
        reasons.append(
            "potential sweeps in one direction only; expected a forward/reverse "
            "cycle for this technique"
        )

    current_changes = _sign_changes(measurement.current_a)
    if current_changes == 0:
        reasons.append("no peak or inflection detected in the current trace")

    if reasons:
        return QCRecord(
            filename=filename,
            parse_timestamp=now,
            sanity_status="flagged",
            sanity_reason="; ".join(reasons),
            heuristic_version=HEURISTIC_VERSION,
        )

    return QCRecord(
        filename=filename,
        parse_timestamp=now,
        sanity_status="ok",
        sanity_reason=None,
        heuristic_version=HEURISTIC_VERSION,
    )
