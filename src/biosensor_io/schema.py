"""Shared output schema for parsed electrochemical measurements.

Every reader converts its instrument-specific format into a `Measurement`.
QC state lives in a separate `QCRecord` so sanity-check logic can evolve
without touching the measurement schema itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

SCHEMA_VERSION = "1.0"


@dataclass
class Measurement:
    potential_v: list[float]
    current_a: list[float]
    scan_rate_v_s: Optional[float] = None
    cycle_number: Optional[list[int]] = None
    technique: Optional[str] = None
    sample_id: Optional[str] = None
    analyte_name: Optional[str] = None
    analyte_concentration: Optional[float] = None
    concentration_unit: Optional[str] = None
    timestamp: Optional[datetime] = None
    replicate_id: Optional[str] = None
    technique_params: dict[str, Any] = field(default_factory=dict)
    instrument_source: str = "unknown"
    source_filename: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if len(self.potential_v) != len(self.current_a):
            raise ValueError(
                f"potential_v ({len(self.potential_v)} points) and current_a "
                f"({len(self.current_a)} points) must be the same length"
            )
        if self.cycle_number is not None and len(self.cycle_number) != len(self.potential_v):
            raise ValueError("cycle_number length must match potential_v length")

    @property
    def n_points(self) -> int:
        return len(self.potential_v)


@dataclass
class QCRecord:
    """Per-file sanity-check state, kept separate from the measurement data."""

    filename: str
    parse_timestamp: datetime
    sanity_status: str = "unreviewed"  # "ok" | "flagged" | "failed" | "unreviewed"
    sanity_reason: Optional[str] = None
    reviewed_by: Optional[str] = None
    heuristic_version: str = "0.1"

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["parse_timestamp"] = self.parse_timestamp.isoformat()
        return d
