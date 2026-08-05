"""Public API: load(), to_dataframe(), batch_load()."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from biosensor_io.qc import sanity_check
from biosensor_io.readers.base import ParseError
from biosensor_io.readers.detect import detect_reader
from biosensor_io.readers.base import UnsupportedFormatError
from biosensor_io.schema import Measurement, QCRecord


@dataclass
class LoadResult:
    measurement: Measurement
    qc: QCRecord


def load(filepath: str | os.PathLike) -> LoadResult:
    """Load a single instrument export file, auto-detecting its format."""
    path = Path(filepath)
    raw = path.read_bytes()
    reader = detect_reader(raw, path.name)
    measurement = reader.parse(raw, path.name)
    qc = sanity_check(measurement)
    return LoadResult(measurement=measurement, qc=qc)


def to_dataframe(measurement: Measurement) -> pd.DataFrame:
    """Expand a Measurement into a long-form dataframe, one row per data point."""
    n = measurement.n_points
    return pd.DataFrame(
        {
            "potential_v": measurement.potential_v,
            "current_a": measurement.current_a,
            "cycle_number": measurement.cycle_number or [None] * n,
            "scan_rate_v_s": [measurement.scan_rate_v_s] * n,
            "technique": [measurement.technique] * n,
            "sample_id": [measurement.sample_id] * n,
            "analyte_name": [measurement.analyte_name] * n,
            "analyte_concentration": [measurement.analyte_concentration] * n,
            "concentration_unit": [measurement.concentration_unit] * n,
            "timestamp": [measurement.timestamp] * n,
            "replicate_id": [measurement.replicate_id] * n,
            "instrument_source": [measurement.instrument_source] * n,
            "source_filename": [measurement.source_filename] * n,
            "schema_version": [measurement.schema_version] * n,
        }
    )


@dataclass
class BatchLoadResult:
    results: list[LoadResult]
    errors: list[tuple[str, str]]  # (filename, error message)

    def to_dataframe(self) -> pd.DataFrame:
        frames = [to_dataframe(r.measurement) for r in self.results]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def qc_dataframe(self) -> pd.DataFrame:
        rows = [r.qc.as_dict() for r in self.results]
        for filename, message in self.errors:
            rows.append(
                {
                    "filename": filename,
                    "parse_timestamp": None,
                    "sanity_status": "failed",
                    "sanity_reason": message,
                    "reviewed_by": None,
                    "heuristic_version": None,
                }
            )
        return pd.DataFrame(rows)


def batch_load(directory: str | os.PathLike) -> BatchLoadResult:
    """Load every file in a directory, collecting per-file results and errors.

    A single bad file never aborts the batch: it's recorded in `.errors`
    (and surfaced in the QC table as sanity_status="failed") so the rest of
    the folder still loads.
    """
    dir_path = Path(directory)
    results: list[LoadResult] = []
    errors: list[tuple[str, str]] = []

    for entry in sorted(dir_path.iterdir()):
        if not entry.is_file():
            continue
        try:
            results.append(load(entry))
        except (ParseError, UnsupportedFormatError, ValueError, OSError) as e:
            errors.append((entry.name, str(e)))
        except Exception:
            # A single malformed/hostile file must never abort the batch.
            errors.append((entry.name, "file could not be parsed (unexpected format or corrupt data)"))

    return BatchLoadResult(results=results, errors=errors)
