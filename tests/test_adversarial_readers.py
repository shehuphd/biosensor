"""Adversarial cases for the readers and core parsing path: malformed,
truncated, oversized, wrongly-encoded, and boundary-value input. Per
CODING.md, a defense (a size cap, a sanitizer, a bounded walk) is only
verified once there's a test that actually exercises the failure mode it
exists for.
"""

from __future__ import annotations

import json

import pytest

from biosensor.qc import sanity_check
from biosensor.readers.base import (
    MAX_DATA_ROWS,
    MAX_FILE_BYTES,
    ParseError,
    UnsupportedFormatError,
)
from biosensor.readers.ch_instruments import CHInstrumentsReader
from biosensor.readers.detect import detect_reader
from biosensor.readers.generic_csv import GenericCSVReader
from biosensor.readers.palmsens import PalmSensReader


# ---------------------------------------------------------------- empty / truncated / garbage input

def test_empty_file_is_unsupported():
    with pytest.raises(UnsupportedFormatError):
        detect_reader(b"", "empty.csv")


def test_whitespace_only_file_is_unsupported():
    with pytest.raises(UnsupportedFormatError):
        detect_reader(b"   \n\n   \n", "blank.csv")


def test_truncated_chi_header_with_no_data_rows_raises():
    raw = (
        b"CHI Electrochemical Workstation\n"
        b"Instrument Model: CHI600E\n"
        b"Init E (V) = -0.5\n"
        b"Potential/V, Current/A\n"
        # file cuts off here, no data rows at all
    )
    reader = CHInstrumentsReader()
    assert reader.sniff(raw, "truncated.txt") is True
    with pytest.raises(ParseError):
        reader.parse(raw, "truncated.txt")


def test_binary_garbage_is_not_misidentified_as_any_format():
    raw = bytes(random_byte for random_byte in range(0, 256)) * 4
    with pytest.raises(UnsupportedFormatError):
        detect_reader(raw, "garbage.bin")


def test_non_utf8_bytes_do_not_crash_generic_csv_sniff():
    # Invalid UTF-8 and invalid latin-1-decodable-but-nonsensical content
    # must degrade to "not this format," never raise out of sniff().
    raw = b"\xff\xfe\x00\x01potential_v,current_a\n\xfa\xfb,\xfc\xfd\n"
    reader = GenericCSVReader()
    assert reader.sniff(raw, "bad_encoding.csv") in (True, False)  # must not raise


# ---------------------------------------------------------------- size limits actually enforced

def test_file_over_byte_limit_is_rejected():
    # A well-formed generic CSV, but padded past MAX_FILE_BYTES.
    header = "potential_v,current_a\n"
    row = "0.1,1e-6\n"
    padding_rows_needed = (MAX_FILE_BYTES // len(row)) + 10
    raw = (header + row * padding_rows_needed).encode()
    assert len(raw) > MAX_FILE_BYTES

    reader = GenericCSVReader()
    with pytest.raises(ParseError, match="exceeds"):
        reader.parse(raw, "huge.csv")


def test_data_rows_over_max_is_rejected():
    header = "potential_v,current_a\n"
    rows = "".join(f"{i * 0.0001},1e-6\n" for i in range(MAX_DATA_ROWS + 100))
    raw = (header + rows).encode()

    reader = GenericCSVReader()
    with pytest.raises(ParseError, match="row limit"):
        reader.parse(raw, "too_many_rows.csv")


def test_palmsens_deeply_nested_json_does_not_hang_or_crash():
    # A pathologically nested JSON payload. Python's json module has its
    # own recursion handling; this must surface as a parse failure, not
    # an uncaught RecursionError bubbling out of the reader.
    depth = 5000
    nested = "{\"a\":" * depth + "1" + "}" * depth
    raw = nested.encode()
    reader = PalmSensReader()
    with pytest.raises(Exception):  # noqa: B017 - any controlled failure is acceptable here
        reader.parse(raw, "evil.pssession")


def test_palmsens_huge_flat_array_is_rejected():
    doc = {
        "Measurements": [
            {
                "Method": {"Name": "CV"},
                "DataSet": {
                    "Values": [
                        {"Type": "Potential", "DataValues": [{"V": 0.1}] * (MAX_DATA_ROWS + 10)},
                        {"Type": "Current", "DataValues": [{"V": 1e-6}] * (MAX_DATA_ROWS + 10)},
                    ]
                },
            }
        ]
    }
    raw = json.dumps(doc).encode()
    reader = PalmSensReader()
    with pytest.raises(ParseError, match="row limit"):
        reader.parse(raw, "huge.pssession")


# ---------------------------------------------------------------- malformed / hostile JSON

def test_palmsens_non_json_content_raises_parse_error():
    reader = PalmSensReader()
    with pytest.raises(ParseError):
        reader.parse(b"{not: valid json!!!", "broken.pssession")


def test_palmsens_json_without_measurements_key_raises():
    reader = PalmSensReader()
    with pytest.raises(ParseError):
        reader.parse(json.dumps({"unrelated": "data"}).encode(), "wrong_shape.pssession")


def test_palmsens_missing_data_arrays_raises():
    doc = {"Measurements": [{"Method": {"Name": "CV"}, "DataSet": {"Values": []}}]}
    reader = PalmSensReader()
    with pytest.raises(ParseError):
        reader.parse(json.dumps(doc).encode(), "no_data.pssession")


# ---------------------------------------------------------------- boundary values: NaN / Inf get flagged, not silently accepted

def test_nan_and_inf_values_are_caught_by_qc_not_silently_passed():
    raw = (
        b"potential_v,current_a\n"
        b"-0.1,1e-6\n"
        b"0.0,nan\n"
        b"0.1,inf\n"
        b"0.2,1e-6\n"
        b"0.3,1e-6\n"
    )
    reader = GenericCSVReader()
    measurement = reader.parse(raw, "nan_inf.csv")
    qc = sanity_check(measurement)
    assert qc.sanity_status == "failed"
    assert "nan" in qc.sanity_reason.lower() or "infinite" in qc.sanity_reason.lower()


def test_extreme_negative_and_positive_potential_values_still_parse():
    raw = (
        b"potential_v,current_a\n"
        b"-1e10,1e-6\n"
        b"0.0,5e-6\n"
        b"1e10,1e-6\n"
        b"0.1,1e-6\n"
        b"0.2,1e-6\n"
    )
    reader = GenericCSVReader()
    measurement = reader.parse(raw, "extreme.csv")
    assert measurement.n_points == 5
    qc = sanity_check(measurement)
    assert "unusually wide" in (qc.sanity_reason or "")


# ---------------------------------------------------------------- header-derived string fields are bounded

def test_ch_instruments_header_with_no_column_names_falls_back_safely():
    raw = (
        b"CHI Electrochemical Workstation\n"
        b"Instrument Model: CHI600E\n"
        b"Potential/V, Current/A\n"
        b"-0.5,1e-7\n"
        b"-0.4,1e-7\n"
        b"-0.3,5e-6\n"
        b"-0.2,1e-7\n"
        b"-0.1,1e-7\n"
    )
    reader = CHInstrumentsReader()
    measurement = reader.parse(raw, "ok.txt")
    assert measurement.n_points == 5
    mapping = measurement.technique_params.get("_column_mapping")
    assert mapping is not None
    assert "potential_v" in mapping and "current_a" in mapping


# ---------------------------------------------------------------- columns must never desync

def test_generic_csv_row_with_unparseable_current_is_skipped_wholesale():
    # A row whose potential is numeric but whose current is not must drop the
    # whole row. Appending potential alone would leave the two columns unequal
    # in length, which Measurement rejects with a ValueError that would escape
    # as an unhandled crash from load().
    raw = (
        b"potential_v,current_a\n"
        b"0.10,1e-6\n"
        b"0.20,not_a_number\n"  # potential valid, current junk
        b"0.30,3e-6\n"
        b"0.40,4e-6\n"
        b"0.50,5e-6\n"
        b"0.60,6e-6\n"
    )
    measurement = GenericCSVReader().parse(raw, "desync.csv")
    assert len(measurement.potential_v) == len(measurement.current_a)
    assert measurement.n_points == 5  # the junk-current row is gone
    assert 0.2 not in measurement.potential_v


# ---------------------------------------------------------------- deep JSON is a bounded failure

def test_deeply_nested_palmsens_json_raises_parse_error_not_recursion():
    # A pathologically nested document either makes json.loads raise
    # RecursionError (older parsers) or parses to a structure whose first
    # measurement isn't an object (newer C scanners). Either way the reader
    # must surface a ParseError, never an unhandled RecursionError/AttributeError.
    payload = "0"
    for _ in range(3000):
        payload = "[" + payload + "]"
    raw = ('{"Measurements":' + payload + "}").encode()
    with pytest.raises(ParseError):
        PalmSensReader().parse(raw, "deep.pssession")


# ---------------------------------------------------------------- extension is never trusted alone

def test_csv_misnamed_pssession_falls_through_to_generic():
    # A ".pssession" extension is a hint, not a pass: a file whose content is
    # plainly CSV must not be routed to the PalmSens (JSON) reader.
    raw = (
        b"Potential (V),Current (A)\n"
        b"-0.5,1e-7\n-0.4,2e-7\n-0.3,5e-6\n-0.2,2e-7\n-0.1,1e-7\n"
    )
    assert PalmSensReader().sniff(raw, "actually_csv.pssession") is False
    assert detect_reader(raw, "actually_csv.pssession").name == "generic_csv"


def test_palmsens_mismatched_array_lengths_are_rejected_not_truncated():
    # Unequal potential/current arrays mean the walk paired series from two
    # different curves. Truncating to the shorter would misalign every point;
    # the reader rejects instead of guessing.
    doc = {
        "Measurements": [
            {
                "DataSet": {
                    "Values": [
                        {"Type": "Potential", "DataValues": [0.1, 0.2, 0.3, 0.4, 0.5]},
                        {"Type": "Current", "DataValues": [1e-6, 2e-6, 3e-6]},
                    ]
                }
            }
        ]
    }
    raw = json.dumps(doc).encode()
    with pytest.raises(ParseError):
        PalmSensReader().parse(raw, "mismatch.pssession")


def test_nova_current_regex_rejects_current_in_volts():
    # "I /V" is not a current column on any instrument; the regex must not bind
    # it (it used to, from a stray alternative), while "I /A" still matches.
    from biosensor.readers.metrohm_nova import _CURRENT_HEADER_RE

    assert _CURRENT_HEADER_RE.search("I /A")
    assert _CURRENT_HEADER_RE.search("WE(1).Current (A)")
    assert not _CURRENT_HEADER_RE.search("I /V")
