"""Metrohm Nova (Autolab) text/CSV export reader.

Nova's export uses a semicolon- or tab-delimited table, typically with
column names like "WE(1).Potential (V)" / "WE(1).Current (A)" or the
shorter "E /V" / "I /A", sometimes preceded by a few metadata lines
mentioning Autolab/Nova.
"""

from __future__ import annotations

import csv
import io
import re

from biosensor.readers.base import (
    MAX_DATA_ROWS,
    FileTooLargeError,
    ParseError,
    Reader,
    enforce_size_limit,
)
from biosensor.schema import Measurement

_POTENTIAL_HEADER_RE = re.compile(r"(we\(1\)\.)?potential|^e\s*/\s*v$", re.IGNORECASE)
_CURRENT_HEADER_RE = re.compile(r"(we\(1\)\.)?current|^i\s*/\s*a$", re.IGNORECASE)
_SCAN_HEADER_RE = re.compile(r"^scan$|^cycle", re.IGNORECASE)
_SIGNATURE_HINTS = ("autolab", "nova", "metrohm", "we(1).potential", "we(1).current")


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("could not decode file as text")


def _sniff_delimiter(line: str) -> str:
    if line.count(";") >= line.count(",") and line.count(";") >= line.count("\t"):
        return ";"
    if line.count("\t") >= line.count(","):
        return "\t"
    return ","


def _find_header_row(lines: list[str]) -> tuple[int, str] | None:
    for i, line in enumerate(lines[:50]):
        delim = _sniff_delimiter(line)
        cells = [c.strip() for c in line.split(delim)]
        has_pot = any(_POTENTIAL_HEADER_RE.search(c) for c in cells)
        has_cur = any(_CURRENT_HEADER_RE.search(c) for c in cells)
        if has_pot and has_cur:
            return i, delim
    return None


class MetrohmNovaReader(Reader):
    name = "metrohm_nova"

    def sniff(self, raw: bytes, filename: str) -> bool:
        try:
            text = _decode(raw[:8192])
        except ParseError:
            return False
        lower = text.lower()
        lines = text.splitlines()
        header = _find_header_row(lines)
        if header is None:
            return False
        hint_hit = any(hint in lower for hint in _SIGNATURE_HINTS)
        strong_columns = "we(1).potential" in lower or "we(1).current" in lower
        return hint_hit or strong_columns

    def parse(self, raw: bytes, filename: str) -> Measurement:
        enforce_size_limit(raw, filename)
        text = _decode(raw)
        lines = text.splitlines()

        found = _find_header_row(lines)
        if found is None:
            raise ParseError(
                f"{filename}: recognized as Metrohm Nova format but no "
                f"potential/current header row found"
            )
        header_idx, delimiter = found

        reader = csv.reader(io.StringIO("\n".join(lines[header_idx:])), delimiter=delimiter)
        rows = list(reader)
        header = [h.strip() for h in rows[0]]

        pot_idx = next(i for i, h in enumerate(header) if _POTENTIAL_HEADER_RE.search(h))
        cur_idx = next(i for i, h in enumerate(header) if _CURRENT_HEADER_RE.search(h))
        scan_idx = next((i for i, h in enumerate(header) if _SCAN_HEADER_RE.search(h)), None)

        potential_v: list[float] = []
        current_a: list[float] = []
        cycle_number: list[int] = []

        data_rows = rows[1:]
        if len(data_rows) > MAX_DATA_ROWS:
            raise FileTooLargeError(f"{filename}: exceeds {MAX_DATA_ROWS} row limit")

        for row in data_rows:
            if len(row) <= max(pot_idx, cur_idx):
                continue
            try:
                p = float(row[pot_idx].replace(",", "."))
                c = float(row[cur_idx].replace(",", "."))
            except ValueError:
                continue
            potential_v.append(p)
            current_a.append(c)
            if scan_idx is not None and len(row) > scan_idx:
                try:
                    cycle_number.append(int(float(row[scan_idx])))
                except ValueError:
                    cycle_number.append(1)
            else:
                cycle_number.append(1)

        if not potential_v:
            raise ParseError(f"{filename}: no numeric data rows found")

        metadata: dict[str, str] = {}
        for line in lines[:header_idx]:
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                if key:
                    metadata[key] = val.strip()

        column_mapping = {
            "potential_v": f'col {pot_idx + 1} · "{header[pot_idx]}"',
            "current_a": f'col {cur_idx + 1} · "{header[cur_idx]}"',
        }
        if scan_idx is not None:
            column_mapping["cycle_number"] = f'col {scan_idx + 1} · "{header[scan_idx]}"'
        metadata["_column_mapping"] = column_mapping

        return Measurement(
            potential_v=potential_v,
            current_a=current_a,
            cycle_number=cycle_number if any(c != 1 for c in cycle_number) else None,
            technique_params=metadata,
            instrument_source="metrohm_nova",
            source_filename=filename,
        )
