"""Generic delimited CSV reader.

The fallback reader: any delimited text file with a header row containing
recognizable potential/current column names. Also the format most other
readers' sniff() steps rule *out* before this one is tried.
"""

from __future__ import annotations

import csv
import io

from biosensor_io.readers.base import (
    MAX_DATA_ROWS,
    ParseError,
    Reader,
    enforce_size_limit,
)
from biosensor_io.readers.columns import infer_column_mapping, infer_from_filename
from biosensor_io.schema import Measurement

_SNIFF_SAMPLE_BYTES = 4096


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("could not decode file as text")


class GenericCSVReader(Reader):
    name = "generic_csv"

    def sniff(self, raw: bytes, filename: str) -> bool:
        if len(raw) > 30_000_000:
            return False
        try:
            text = _decode(raw[:_SNIFF_SAMPLE_BYTES])
        except ParseError:
            return False
        sample = text.splitlines()
        if len(sample) < 2:
            return False
        try:
            dialect = csv.Sniffer().sniff(text, delimiters=",;\t")
        except csv.Error:
            dialect = None
        delimiter = dialect.delimiter if dialect else ","
        header = sample[0].split(delimiter)
        mapping = infer_column_mapping([h.strip() for h in header])
        return mapping["potential_v"] is not None and mapping["current_a"] is not None

    def parse(self, raw: bytes, filename: str) -> Measurement:
        enforce_size_limit(raw, filename)
        text = _decode(raw)

        try:
            dialect = csv.Sniffer().sniff(text[:_SNIFF_SAMPLE_BYTES], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(io.StringIO(text), dialect)
        rows = list(reader)
        if not rows:
            raise ParseError(f"{filename}: empty file")

        header = [h.strip() for h in rows[0]]
        mapping = infer_column_mapping(header)
        if mapping["potential_v"] is None or mapping["current_a"] is None:
            raise ParseError(
                f"{filename}: could not identify potential/current columns "
                f"from header {header!r}"
            )

        pot_idx = header.index(mapping["potential_v"])
        cur_idx = header.index(mapping["current_a"])
        sample_idx = header.index(mapping["sample_id"]) if mapping["sample_id"] else None
        conc_idx = (
            header.index(mapping["analyte_concentration"])
            if mapping["analyte_concentration"]
            else None
        )
        unit_idx = (
            header.index(mapping["concentration_unit"])
            if mapping["concentration_unit"]
            else None
        )

        potential_v: list[float] = []
        current_a: list[float] = []
        sample_id = None
        analyte_concentration = None
        concentration_unit = None

        data_rows = rows[1:]
        if len(data_rows) > MAX_DATA_ROWS:
            raise ParseError(
                f"{filename}: {len(data_rows)} data rows exceeds the "
                f"{MAX_DATA_ROWS} row limit"
            )

        for row in data_rows:
            if not row or all(not cell.strip() for cell in row):
                continue
            try:
                potential_v.append(float(row[pot_idx]))
                current_a.append(float(row[cur_idx]))
            except (ValueError, IndexError):
                continue
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

        column_mapping = {
            "potential_v": f'col {pot_idx + 1} · "{header[pot_idx]}"',
            "current_a": f'col {cur_idx + 1} · "{header[cur_idx]}"',
        }
        if mapping["sample_id"]:
            column_mapping["sample_id"] = f'col {sample_idx + 1} · "{header[sample_idx]}"'

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
