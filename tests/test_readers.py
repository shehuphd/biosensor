from pathlib import Path

import pytest

from biosensor.readers.base import UnsupportedFormatError
from biosensor.readers.detect import detect_reader

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_ch_instruments_detected_and_parsed():
    raw = _load("chi_sample.txt")
    reader = detect_reader(raw, "chi_sample.txt")
    assert reader.name == "ch_instruments"

    m = reader.parse(raw, "chi_sample.txt")
    assert m.n_points == 41
    assert m.instrument_source == "ch_instruments"
    assert m.scan_rate_v_s == pytest.approx(0.1)
    assert min(m.potential_v) == pytest.approx(-0.5)
    assert max(m.potential_v) == pytest.approx(0.5)
    assert max(m.current_a) > 1e-6  # the synthetic peak


def test_metrohm_nova_detected_and_parsed():
    raw = _load("nova_sample.csv")
    reader = detect_reader(raw, "nova_sample.csv")
    assert reader.name == "metrohm_nova"

    m = reader.parse(raw, "nova_sample.csv")
    assert m.n_points == 41
    assert m.instrument_source == "metrohm_nova"


def test_palmsens_detected_and_parsed():
    raw = _load("palmsens_sample.pssession")
    reader = detect_reader(raw, "palmsens_sample.pssession")
    assert reader.name == "palmsens"

    m = reader.parse(raw, "palmsens_sample.pssession")
    assert m.n_points == 41
    assert m.scan_rate_v_s == pytest.approx(0.1)
    assert m.instrument_source == "palmsens"


def test_generic_csv_detected_and_parsed():
    raw = _load("generic_sample.csv")
    reader = detect_reader(raw, "generic_sample.csv")
    assert reader.name == "generic_csv"

    m = reader.parse(raw, "generic_sample.csv")
    assert m.n_points == 41
    assert m.sample_id == "sample_A"
    assert m.analyte_concentration == pytest.approx(10.0)
    assert m.concentration_unit == "nM"


def test_unrecognized_format_raises():
    raw = _load("bad_sample.txt")
    with pytest.raises(UnsupportedFormatError):
        detect_reader(raw, "bad_sample.txt")
