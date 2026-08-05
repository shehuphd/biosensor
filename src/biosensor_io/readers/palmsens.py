"""PalmSens (.pssession) reader.

.pssession files are JSON documents (PSTrace's native session format).
This reader targets the commonly-seen structure: a top-level
"Measurements" list, each with a "DataSet" containing typed value arrays
(one array tagged as the potential series, one as the current series) plus
a "Method" block for technique metadata.

PalmSens does not publish a stable public schema for this format, so this
reader is intentionally lenient: it walks the parsed JSON looking for
arrays whose type label matches "potential" / "current" rather than
assuming one exact shape. Treat this as best-effort coverage, consistent
with the PRD's "four readers, not exhaustive vendor support" scope — files
from unusual PSTrace versions may need the generic CSV path instead (most
PalmSens software can also export CSV directly).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from biosensor_io.readers.base import (
    MAX_DATA_ROWS,
    ParseError,
    Reader,
    enforce_size_limit,
)
from biosensor_io.schema import Measurement

_POTENTIAL_TYPE_HINTS = ("potential", "voltage", "ewe")
_CURRENT_TYPE_HINTS = ("current",)
_MAX_WALK_NODES = 50_000


def _safe_json_loads(text: str, filename: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ParseError(f"{filename}: not valid JSON ({e})") from e


def _extract_numeric_array(node: Any) -> Optional[list[float]]:
    if isinstance(node, list) and node and all(
        isinstance(v, (int, float)) for v in node[:5]
    ):
        try:
            return [float(v) for v in node]
        except (TypeError, ValueError):
            return None
    if isinstance(node, list) and node and all(isinstance(v, dict) for v in node[:5]):
        for key in ("V", "Value", "value", "v"):
            values = [v.get(key) for v in node if isinstance(v, dict)]
            if values and all(isinstance(v, (int, float)) for v in values):
                return [float(v) for v in values]
    return None


def _walk_for_series(node: Any, budget: list[int]) -> dict[str, list[float]]:
    """Depth-first search for arrays tagged with a Potential/Current type label."""
    found: dict[str, list[float]] = {}
    stack = [node]
    while stack:
        budget[0] -= 1
        if budget[0] <= 0:
            break
        current = stack.pop()
        if isinstance(current, dict):
            type_label = str(
                current.get("Type") or current.get("type") or current.get("Name") or ""
            ).lower()
            values_node = (
                current.get("DataValues")
                or current.get("Values")
                or current.get("values")
                or current.get("Data")
            )
            array = _extract_numeric_array(values_node) if values_node is not None else None
            if array:
                if any(h in type_label for h in _POTENTIAL_TYPE_HINTS) and "potential" not in found:
                    found["potential"] = array
                elif any(h in type_label for h in _CURRENT_TYPE_HINTS) and "current" not in found:
                    found["current"] = array
            for v in current.values():
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    stack.append(item)
    return found


class PalmSensReader(Reader):
    name = "palmsens"

    def sniff(self, raw: bytes, filename: str) -> bool:
        if filename.lower().endswith(".pssession"):
            return True
        head = raw[:2048].lstrip()
        if not head.startswith(b"{"):
            return False
        lower = raw[:8192].lower()
        return b"measurements" in lower and (b"palmsens" in lower or b"pstrace" in lower or b"dataset" in lower)

    def parse(self, raw: bytes, filename: str) -> Measurement:
        enforce_size_limit(raw, filename)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise ParseError(f"{filename}: not valid UTF-8 JSON ({e})") from e

        doc = _safe_json_loads(text, filename)

        measurements = doc.get("Measurements") if isinstance(doc, dict) else None
        if not measurements:
            raise ParseError(f"{filename}: no 'Measurements' found in .pssession JSON")

        measurement_node = measurements[0]
        budget = [_MAX_WALK_NODES]
        series = _walk_for_series(measurement_node.get("DataSet", measurement_node), budget)

        potential_v = series.get("potential")
        current_a = series.get("current")
        if not potential_v or not current_a:
            raise ParseError(
                f"{filename}: could not locate potential/current arrays in "
                f"PalmSens session data"
            )
        if len(potential_v) > MAX_DATA_ROWS or len(current_a) > MAX_DATA_ROWS:
            raise ParseError(f"{filename}: exceeds {MAX_DATA_ROWS} row limit")

        n = min(len(potential_v), len(current_a))
        potential_v, current_a = potential_v[:n], current_a[:n]

        method = measurement_node.get("Method", {}) if isinstance(measurement_node, dict) else {}
        technique = measurement_node.get("Title") or method.get("Name")
        scan_rate = method.get("Scanrate") or method.get("ScanRate")
        try:
            scan_rate = float(scan_rate) if scan_rate is not None else None
        except (TypeError, ValueError):
            scan_rate = None

        return Measurement(
            potential_v=potential_v,
            current_a=current_a,
            scan_rate_v_s=scan_rate,
            technique=str(technique) if technique else None,
            technique_params={k: v for k, v in method.items() if isinstance(v, (str, int, float))},
            instrument_source="palmsens",
            source_filename=filename,
        )
