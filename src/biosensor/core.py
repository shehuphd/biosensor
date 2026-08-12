"""Public API: load(), to_dataframe(), batch_load()."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from biosensor.qc import sanity_check
from biosensor.readers.base import (
    MAX_FILE_BYTES,
    FileTooLargeError,
    ParseError,
    UnsupportedFormatError,
    classify_error,
)
from biosensor.readers.detect import detect_reader
from biosensor.schema import Measurement, QCRecord


@dataclass
class LoadResult:
    measurement: Measurement
    qc: QCRecord


def load(filepath: str | os.PathLike) -> LoadResult:
    """Load a single instrument export file, auto-detecting its format."""
    path = Path(filepath)
    # Check size on disk before reading, so a huge file in a batch folder is
    # rejected without first being pulled into memory in full.
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise FileTooLargeError(
            f"{path.name}: file is {size} bytes, exceeds the "
            f"{MAX_FILE_BYTES} byte limit for parsing"
        )
    raw = path.read_bytes()
    reader = detect_reader(raw, path.name)
    measurement = reader.parse(raw, path.name)
    qc = sanity_check(measurement)
    return LoadResult(measurement=measurement, qc=qc)


def to_dataframe(measurement: Measurement) -> pd.DataFrame:
    """Expand a Measurement into a long-form dataframe, one row per data point."""
    n = measurement.n_points
    # Optional numeric columns get an explicit float64 dtype so an all-None
    # column (a measurement missing that field) stays numeric rather than
    # object, which keeps batch concat from mixing dtypes across files.
    def float_na(values):
        return pd.Series(values, dtype="float64")

    return pd.DataFrame(
        {
            "potential_v": measurement.potential_v,
            "current_a": measurement.current_a,
            "cycle_number": float_na(measurement.cycle_number or [None] * n),
            "scan_rate_v_s": float_na([measurement.scan_rate_v_s] * n),
            "technique": [measurement.technique] * n,
            "sample_id": [measurement.sample_id] * n,
            "analyte_name": [measurement.analyte_name] * n,
            "analyte_concentration": float_na([measurement.analyte_concentration] * n),
            "concentration_unit": [measurement.concentration_unit] * n,
            "timestamp": [measurement.timestamp] * n,
            "replicate_id": [measurement.replicate_id] * n,
            "instrument_source": [measurement.instrument_source] * n,
            "source_filename": [measurement.source_filename] * n,
            "schema_version": [measurement.schema_version] * n,
        }
    )


@dataclass
class BatchError:
    """One file that failed to load, with a category for grouping/filtering.

    `category` is one of the values in `readers.base.ERROR_CATEGORIES`
    (unsupported / parse / too_large / corrupt / unexpected).
    """

    filename: str
    message: str
    category: str


@dataclass
class BatchLoadResult:
    results: list[LoadResult]
    errors: list[BatchError]

    def to_dataframe(self) -> pd.DataFrame:
        frames = [to_dataframe(r.measurement) for r in self.results]
        frames = [f for f in frames if not f.empty]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def qc_dataframe(self) -> pd.DataFrame:
        rows = []
        for r in self.results:
            row = r.qc.as_dict()
            row["error_category"] = None
            rows.append(row)
        for err in self.errors:
            rows.append(
                {
                    "filename": err.filename,
                    "parse_timestamp": None,
                    "sanity_status": "failed",
                    "sanity_reason": err.message,
                    "reviewed_by": None,
                    "heuristic_version": None,
                    "error_category": err.category,
                }
            )
        return pd.DataFrame(rows)


def batch_load(directory: str | os.PathLike) -> BatchLoadResult:
    """Load every file in a directory, collecting per-file results and errors.

    A single bad file never aborts the batch: it's recorded in `.errors` as a
    `BatchError` (and surfaced in the QC table as sanity_status="failed") so
    the rest of the folder still loads.
    """
    dir_path = Path(directory)
    results: list[LoadResult] = []
    errors: list[BatchError] = []

    for entry in sorted(dir_path.iterdir()):
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            # Skip OS/editor cruft (.DS_Store, .gitkeep, ...) so it doesn't add
            # a spurious error to every batch loaded from a macOS folder.
            continue
        try:
            results.append(load(entry))
        except (ParseError, UnsupportedFormatError, ValueError, OSError) as e:
            errors.append(BatchError(entry.name, str(e), classify_error(e)))
        except Exception as e:
            # A single malformed/hostile file must never abort the batch. The
            # exception type is safe to name (it isn't file content); the raw
            # message is not surfaced, since an unforeseen error could echo
            # untrusted input back into the output.
            errors.append(
                BatchError(
                    entry.name,
                    f"file could not be parsed (unexpected {type(e).__name__})",
                    "unexpected",
                )
            )

    return BatchLoadResult(results=results, errors=errors)
