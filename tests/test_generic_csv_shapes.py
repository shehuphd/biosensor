"""CSV shapes the generic reader must handle, drawn from published
potentiostat/analysis-tool exports: a header row, one or more metadata lines
before the header, and no header at all. Anything it can't read as
potential/current is rejected rather than guessed at.
"""

from __future__ import annotations

import pytest

from biosensor.readers.base import ParseError, UnsupportedFormatError
from biosensor.readers.detect import detect_reader
from biosensor.readers.generic_csv import GenericCSVReader


def _sweep_rows(n: int) -> list[str]:
    return [f"{-0.3 + 0.01 * i:.3f},{(i - n // 2) * 1e-7:.3e}" for i in range(n)]


def test_headerless_two_column_numeric_is_read_by_position():
    # Many exports have no header: the field convention is col 1 = potential,
    # col 2 = current. (Shape taken from PySimpleCV's example_CV.csv.)
    raw = ("\n".join(_sweep_rows(40)) + "\n").encode()
    measurement = GenericCSVReader().parse(raw, "headerless.csv")
    assert measurement.instrument_source == "generic_csv"
    assert measurement.n_points == 40
    assert detect_reader(raw, "headerless.csv").name == "generic_csv"


def test_headerless_tab_delimited_is_read_by_position():
    rows = [r.replace(",", "\t") + "\t" for r in _sweep_rows(40)]  # trailing tab, as seen in exported .txt
    raw = ("\n".join(rows) + "\n").encode()
    measurement = GenericCSVReader().parse(raw, "headerless.txt")
    assert measurement.n_points == 40


def test_metadata_line_before_header_is_skipped():
    # A scan-rate line precedes the "E (V),I (A)" header, with a BOM.
    # (Shape taken from SD-fitter's sample CSVs.)
    raw = (
        "scan rate (V/s),1\n"
        "E (V),I (A)\n" + "\n".join(_sweep_rows(50)) + "\n"
    ).encode("utf-8-sig")
    measurement = GenericCSVReader().parse(raw, "with_preamble.csv")
    assert measurement.n_points == 50
    mapping = measurement.technique_params["_column_mapping"]
    assert "E (V)" in mapping["potential_v"]


def test_non_electrochemical_two_column_text_is_rejected():
    # Headerless support must not swallow arbitrary two-column text files.
    raw = b"name,city\nAlice,Lagos\nBob,Accra\nCara,Nairobi\n"
    with pytest.raises(UnsupportedFormatError):
        detect_reader(raw, "people.csv")


@pytest.mark.parametrize(
    "header",
    [
        "Potential (V),Current (mA)",  # the spelling that silently mis-scaled
        "Voltage (mV),Current (A)",    # non-base potential too
        "Ewe/V,<I>/mA",                # BioLogic-style, name hint misses current
        "Ewe/V,I/mA",
    ],
)
def test_nonbase_unit_is_rejected_not_misscaled(header):
    # We don't convert units yet. A hint-matched column labelled in a non-base
    # unit (mA, mV, ...) must be rejected, never stored 1000x off. The reader
    # claims the file (so the user gets a reason) and fails at parse.
    raw = (header + "\n" + "\n".join(_sweep_rows(30)) + "\n").encode()
    reader = detect_reader(raw, "biologic.csv")
    assert reader.name == "generic_csv"
    with pytest.raises(ParseError):
        reader.parse(raw, "biologic.csv")


def test_base_units_still_parse():
    # The base-unit spellings the non-base guard must not touch.
    for header in ("Potential (V),Current (A)", "Ewe/V,I/A"):
        raw = (header + "\n" + "\n".join(_sweep_rows(30)) + "\n").encode()
        m = GenericCSVReader().parse(raw, "base.csv")
        assert m.n_points == 30
