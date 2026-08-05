"""Format auto-detection: try each reader's sniff() against file content.

Order matters only as a tie-breaker — sniff() is written per-reader to be
specific enough that false positives are rare. Generic CSV is tried last
since it's the most permissive.
"""

from __future__ import annotations

from biosensor_io.readers.base import Reader, UnsupportedFormatError
from biosensor_io.readers.ch_instruments import CHInstrumentsReader
from biosensor_io.readers.generic_csv import GenericCSVReader
from biosensor_io.readers.metrohm_nova import MetrohmNovaReader
from biosensor_io.readers.palmsens import PalmSensReader

READERS: list[Reader] = [
    PalmSensReader(),
    CHInstrumentsReader(),
    MetrohmNovaReader(),
    GenericCSVReader(),
]


def detect_reader(raw: bytes, filename: str) -> Reader:
    for reader in READERS:
        try:
            if reader.sniff(raw, filename):
                return reader
        except Exception:
            continue
    raise UnsupportedFormatError(
        f"{filename}: could not detect a matching format reader "
        f"(tried {', '.join(r.name for r in READERS)})"
    )
