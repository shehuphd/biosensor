"""Manual column-mapping correction for delimited text exports.

Backs the "Correct column mapping" flow: when a file's auto-inferred column
mapping is wrong (e.g. potential/current columns swapped), the user picks the
right columns by index and this module re-parses the raw bytes against that
explicit mapping, bypassing the header-keyword inference that got it wrong.

Only meaningful for delimited-text sources (generic_csv, ch_instruments,
metrohm_nova). PalmSens (.pssession, JSON) has no "columns" to remap.
"""

from __future__ import annotations

import csv
import io

from biosensor.readers.base import MAX_DATA_ROWS, ParseError
from biosensor.readers.ch_instruments import _DATA_HEADER_RE as _CHI_DATA_HEADER_RE
from biosensor.readers.columns import infer_from_filename
from biosensor.readers.metrohm_nova import _find_header_row as _nova_find_header_row
from biosensor.schema import Measurement

CORRECTABLE_SOURCES = {"generic_csv", "ch_instruments", "metrohm_nova"}

POTENTIAL_UNITS = {"V": 1.0, "mV": 1e-3}
CURRENT_UNITS = {"A": 1.0, "mA": 1e-3, "uA": 1e-6, "nA": 1e-9, "pA": 1e-12}

MAX_PREVIEW_ROWS = 8


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("could not decode file as text")


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        if sample.count(";") > sample.count(","):
            return ";"
        if sample.count("\t") > sample.count(","):
            return "\t"
        return ","


def _skip_preamble(text: str, instrument_source: str) -> str:
    """Drop instrument-metadata lines above the actual data table.

    CH Instruments and Metrohm Nova exports both prefix the numeric data
    with a block of "Key = Value" (or free-text) metadata lines. Reuse each
    reader's own header-detection so the correction UI's raw preview shows
    the data rows themselves, not a stretch of instrument metadata.
    """
    lines = text.splitlines()
    if instrument_source == "ch_instruments":
        for i, line in enumerate(lines):
            if _CHI_DATA_HEADER_RE.search(line):
                return "\n".join(lines[i:])
    elif instrument_source == "metrohm_nova":
        found = _nova_find_header_row(lines)
        if found is not None:
            header_idx, _ = found
            return "\n".join(lines[header_idx:])
    return text


def read_raw_table(raw: bytes, filename: str, instrument_source: str = "generic_csv") -> dict:
    """Best-effort tabular view of a file's raw bytes for the correction UI."""
    text = _skip_preamble(_decode(raw), instrument_source)
    delimiter = _sniff_delimiter(text[:4096])
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    non_empty = [r for r in rows if any(cell.strip() for cell in r)]
    n_cols = max((len(r) for r in non_empty[:50]), default=0)
    return {
        "delimiter": delimiter,
        "rows": non_empty,
        "preview_rows": non_empty[:MAX_PREVIEW_ROWS],
        "n_cols": n_cols,
        "total_rows": len(non_empty),
    }


def reparse_with_manual_mapping(
    raw: bytes,
    filename: str,
    instrument_source: str,
    potential_col: int,
    current_col: int,
    cycle_col: int | None,
    potential_unit: str,
    current_unit: str,
) -> Measurement:
    table = read_raw_table(raw, filename, instrument_source)
    pot_mult = POTENTIAL_UNITS.get(potential_unit, 1.0)
    cur_mult = CURRENT_UNITS.get(current_unit, 1.0)

    potential_v: list[float] = []
    current_a: list[float] = []
    cycle_number: list[int] = []

    rows = table["rows"]
    if len(rows) > MAX_DATA_ROWS:
        raise ParseError(f"{filename}: exceeds {MAX_DATA_ROWS} row limit")

    for row in rows:
        if len(row) <= max(potential_col, current_col):
            continue
        try:
            p = float(row[potential_col]) * pot_mult
            c = float(row[current_col]) * cur_mult
        except ValueError:
            continue
        potential_v.append(p)
        current_a.append(c)
        if cycle_col is not None and len(row) > cycle_col:
            try:
                cycle_number.append(int(float(row[cycle_col])))
            except ValueError:
                cycle_number.append(1)
        elif cycle_col is not None:
            cycle_number.append(1)

    if not potential_v:
        raise ParseError(f"{filename}: no numeric rows found for the selected columns")

    fallback = infer_from_filename(filename)

    return Measurement(
        potential_v=potential_v,
        current_a=current_a,
        cycle_number=cycle_number or None,
        sample_id=fallback["sample_id"],
        analyte_concentration=fallback["analyte_concentration"],
        concentration_unit=fallback["concentration_unit"],
        instrument_source=instrument_source,
        source_filename=filename,
    )


def preview_svg_path(measurement: Measurement, width: int = 320, height: int = 140) -> str:
    """A tiny inline sparkline path (potential vs current) for the modal preview."""
    xs, ys = measurement.potential_v, measurement.current_a
    if not xs:
        return ""
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = (x_max - x_min) or 1.0
    y_range = (y_max - y_min) or 1.0
    pad = 8
    points = []
    for x, y in zip(xs, ys):
        px = pad + (x - x_min) / x_range * (width - 2 * pad)
        py = height - pad - (y - y_min) / y_range * (height - 2 * pad)
        points.append((px, py))
    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    step = max(1, len(points) // 200)
    for px, py in points[1::step]:
        d += f" L{px:.1f},{py:.1f}"
    d += f" L{points[-1][0]:.1f},{points[-1][1]:.1f}"
    return d
