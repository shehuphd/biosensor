"""Generic delimited CSV reader.

The fallback reader: any delimited text file whose columns can be read as a
potential/current sweep. Handles three shapes potentiostat exports use:

1. A header row naming the columns (potential/current, and optionally sample
   id / concentration).
2. One or more metadata lines before that header row (a scan-rate line, an
   instrument banner), located by scanning the first lines for the header.
3. No header at all: two or more numeric columns, where the field convention
   is column 1 = potential (V), column 2 = current (A).

Tried last in detection, after the vendor-specific readers rule themselves
out. A file whose columns can't be read as potential/current this way is
rejected, never guessed at.
"""

from __future__ import annotations

import csv
import io

from biosensor.readers.base import (
    MAX_DATA_ROWS,
    FileTooLargeError,
    ParseError,
    Reader,
    enforce_size_limit,
)
from biosensor.readers.columns import infer_column_mapping, infer_from_filename
from biosensor.schema import Measurement

_SNIFF_SAMPLE_BYTES = 4096
_HEADER_SCAN_LINES = 25


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("could not decode file as text")


def _is_number(cell: str) -> bool:
    try:
        float(cell)
        return True
    except ValueError:
        return False


def _sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:_SNIFF_SAMPLE_BYTES], delimiters=",;\t").delimiter
    except csv.Error:
        for line in text.splitlines():
            if line.strip():
                counts = {d: line.count(d) for d in (";", "\t", ",")}
                best = max(counts, key=counts.get)
                return best if counts[best] else ","
        return ","


def _find_header_row(rows: list[list[str]]) -> tuple[int, dict] | None:
    """First row within the scan window that names both a potential and a
    current column. Skips any metadata lines that precede the header."""
    for i, row in enumerate(rows[:_HEADER_SCAN_LINES]):
        mapping = infer_column_mapping([c.strip() for c in row])
        if mapping["potential_v"] is not None and mapping["current_a"] is not None:
            return i, mapping
    return None


def _looks_headerless_numeric(rows: list[list[str]]) -> bool:
    """True if the file has no header row but reads as >=2 numeric columns."""
    checked = 0
    for row in rows:
        cells = [c for c in row if c.strip() != ""]
        if len(cells) < 2:
            continue
        if not (_is_number(cells[0]) and _is_number(cells[1])):
            return False
        checked += 1
        if checked >= 3:
            break
    return checked >= 1


def _build_plan(text: str) -> dict | None:
    """Decide how to read this file, or return None if it can't be read as a
    potential/current table. Shared by sniff() and parse() so detection and
    parsing never disagree."""
    delimiter = _sniff_delimiter(text)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if r]
    if not rows:
        return None

    found = _find_header_row(rows)
    if found is not None:
        header_idx, mapping = found
        header = [c.strip() for c in rows[header_idx]]

        def idx_of(field: str) -> int | None:
            name = mapping[field]
            return header.index(name) if name in header else None

        return {
            "rows": rows,
            "header_idx": header_idx,
            "header": header,
            "mapping": mapping,
            "pot": header.index(mapping["potential_v"]),
            "cur": header.index(mapping["current_a"]),
            "sample": idx_of("sample_id"),
            "conc": idx_of("analyte_concentration"),
            "unit": idx_of("concentration_unit"),
        }

    if _looks_headerless_numeric(rows):
        # No column names to read: fall back to the field convention that
        # column 1 is potential (V) and column 2 is current (A).
        return {
            "rows": rows,
            "header_idx": -1,  # data starts at row 0
            "header": None,
            "mapping": None,
            "pot": 0,
            "cur": 1,
            "sample": None,
            "conc": None,
            "unit": None,
        }

    return None


class GenericCSVReader(Reader):
    name = "generic_csv"

    def sniff(self, raw: bytes, filename: str) -> bool:
        if len(raw) > 30_000_000:
            return False
        try:
            text = _decode(raw[:_SNIFF_SAMPLE_BYTES])
        except ParseError:
            return False
        if len(text.splitlines()) < 2:
            return False
        try:
            return _build_plan(text) is not None
        except Exception:
            return False

    def parse(self, raw: bytes, filename: str) -> Measurement:
        enforce_size_limit(raw, filename)
        text = _decode(raw)

        plan = _build_plan(text)
        if plan is None:
            raise ParseError(
                f"{filename}: could not identify potential/current columns"
            )

        rows = plan["rows"]
        pot_idx, cur_idx = plan["pot"], plan["cur"]
        sample_idx, conc_idx, unit_idx = plan["sample"], plan["conc"], plan["unit"]

        data_rows = rows[plan["header_idx"] + 1:]
        if len(data_rows) > MAX_DATA_ROWS:
            raise FileTooLargeError(
                f"{filename}: {len(data_rows)} data rows exceeds the "
                f"{MAX_DATA_ROWS} row limit"
            )

        potential_v: list[float] = []
        current_a: list[float] = []
        sample_id = None
        analyte_concentration = None
        concentration_unit = None

        for row in data_rows:
            if not row or all(not cell.strip() for cell in row):
                continue
            # Parse both into locals before appending: a row whose potential
            # is numeric but current is not must skip as a unit, or the two
            # columns desync and Measurement rejects the mismatched length.
            try:
                p = float(row[pot_idx])
                c = float(row[cur_idx])
            except (ValueError, IndexError):
                continue
            potential_v.append(p)
            current_a.append(c)
            if sample_idx is not None and sample_id is None and len(row) > sample_idx:
                sample_id = row[sample_idx].strip() or None
            if conc_idx is not None and analyte_concentration is None and len(row) > conc_idx:
                try:
                    analyte_concentration = float(row[conc_idx])
                except ValueError:
                    pass
            if unit_idx is not None and concentration_unit is None and len(row) > unit_idx:
                concentration_unit = row[unit_idx].strip() or None

        if not potential_v:
            raise ParseError(f"{filename}: no numeric data rows found")

        if sample_id is None or analyte_concentration is None:
            fallback = infer_from_filename(filename)
            sample_id = sample_id or fallback["sample_id"]
            analyte_concentration = analyte_concentration or fallback["analyte_concentration"]
            concentration_unit = concentration_unit or fallback["concentration_unit"]

        header = plan["header"]
        if header is not None:
            column_mapping = {
                "potential_v": f'col {pot_idx + 1} · "{header[pot_idx]}"',
                "current_a": f'col {cur_idx + 1} · "{header[cur_idx]}"',
            }
            if plan["mapping"]["sample_id"] and sample_idx is not None:
                column_mapping["sample_id"] = f'col {sample_idx + 1} · "{header[sample_idx]}"'
        else:
            column_mapping = {
                "potential_v": "col 1 (no header)",
                "current_a": "col 2 (no header)",
            }

        return Measurement(
            potential_v=potential_v,
            current_a=current_a,
            sample_id=sample_id,
            analyte_concentration=analyte_concentration,
            concentration_unit=concentration_unit,
            instrument_source="generic_csv",
            source_filename=filename,
            technique_params={"_column_mapping": column_mapping},
        )
