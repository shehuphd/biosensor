"""CH Instruments (CHI) text export reader.

CHI potentiostats export a plain-text file: a block of "Key = Value"
metadata lines, followed by one or more data segments each introduced by a
"Potential/V, Current/A" (or similar) column header line, followed by
comma-separated numeric rows. Multiple segments correspond to multiple scan
cycles.
"""

from __future__ import annotations

import re

from biosensor.readers.base import (
    MAX_DATA_ROWS,
    FileTooLargeError,
    ParseError,
    Reader,
    enforce_size_limit,
)
from biosensor.schema import Measurement

_KV_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 /()%_.-]*?)\s*=\s*(.+?)\s*$")
_DATA_HEADER_RE = re.compile(
    r"potential\s*/?\s*v.*current\s*/?\s*a", re.IGNORECASE
)
_FIELD_SPLIT_RE = re.compile(r"[,\t]+")
_LEADING_NUMBER_RE = re.compile(r"^-?\d")
_SIGNATURE_HINTS = (
    "chi",
    "instrument model",
    "init e (v)",
    "electrochemical workstation",
    "electrochemical analyzer",
)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("could not decode file as text")


class CHInstrumentsReader(Reader):
    name = "ch_instruments"

    def sniff(self, raw: bytes, filename: str) -> bool:
        try:
            text = _decode(raw[:8192]).lower()
        except ParseError:
            return False
        if "init e (v)" in text and _DATA_HEADER_RE.search(text):
            return True
        hint_hits = sum(1 for hint in _SIGNATURE_HINTS if hint in text)
        return hint_hits >= 2 and _DATA_HEADER_RE.search(text) is not None

    def parse(self, raw: bytes, filename: str) -> Measurement:
        enforce_size_limit(raw, filename)
        text = _decode(raw)
        lines = text.splitlines()

        metadata: dict[str, str] = {}
        data_start = None
        header_line = None
        for i, line in enumerate(lines):
            if _DATA_HEADER_RE.search(line):
                data_start = i + 1
                header_line = line.strip()
                break
            m = _KV_RE.match(line)
            if m:
                metadata[m.group(1).strip()] = m.group(2).strip()

        if data_start is None:
            raise ParseError(
                f"{filename}: recognized as CH Instruments format but no "
                f"'Potential/V, Current/A' data header found"
            )

        potential_v: list[float] = []
        current_a: list[float] = []
        cycle_number: list[int] = []
        current_segment = 1

        for line in lines[data_start:]:
            stripped = line.strip()
            if not stripped:
                continue
            if _DATA_HEADER_RE.search(stripped):
                current_segment += 1
                continue
            if "=" in stripped and not _LEADING_NUMBER_RE.match(stripped):
                continue
            parts = _FIELD_SPLIT_RE.split(stripped)
            if len(parts) < 2:
                continue
            try:
                p = float(parts[0])
                c = float(parts[1])
            except ValueError:
                continue
            potential_v.append(p)
            current_a.append(c)
            cycle_number.append(current_segment)
            if len(potential_v) > MAX_DATA_ROWS:
                raise FileTooLargeError(
                    f"{filename}: exceeds {MAX_DATA_ROWS} row limit"
                )

        if not potential_v:
            raise ParseError(f"{filename}: no numeric CV data rows found")

        scan_rate = None
        if "Scan Rate (V/s)" in metadata:
            try:
                scan_rate = float(metadata["Scan Rate (V/s)"])
            except ValueError:
                pass

        technique = None
        for line in lines[:data_start]:
            candidate = line.strip()
            if candidate and "=" not in candidate and len(candidate) < 60:
                if any(
                    kw in candidate.lower()
                    for kw in ("voltammetry", "voltammogram", "amperometry", "chronoamperometry")
                ):
                    technique = candidate
                    break

        header_cols = [c.strip() for c in _FIELD_SPLIT_RE.split(header_line)] if header_line else []
        metadata["_column_mapping"] = {
            "potential_v": f'col 1 · "{header_cols[0]}"' if header_cols else "col 1",
            "current_a": f'col 2 · "{header_cols[1]}"' if len(header_cols) > 1 else "col 2",
        }

        # Sample identity read from the file body, never the filename: these
        # drive the overlay's per-sample grouping and its concentration axis.
        sample_id = metadata.get("Sample ID") or None
        analyte_name = metadata.get("Analyte") or None
        analyte_concentration = None
        concentration_unit = None
        if "Concentration (M)" in metadata:
            try:
                analyte_concentration = float(metadata["Concentration (M)"])
                concentration_unit = "M"
            except ValueError:
                pass

        return Measurement(
            potential_v=potential_v,
            current_a=current_a,
            cycle_number=cycle_number,
            scan_rate_v_s=scan_rate,
            technique=technique,
            sample_id=sample_id,
            analyte_name=analyte_name,
            analyte_concentration=analyte_concentration,
            concentration_unit=concentration_unit,
            technique_params=metadata,
            instrument_source="ch_instruments",
            source_filename=filename,
        )
