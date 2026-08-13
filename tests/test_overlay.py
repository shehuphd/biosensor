"""Overlay tab: content-based sample identity and the overlay figure builder.

The overlay groups curves of one sample and orders them by concentration. Both
halves are covered here: the CH reader reading sample/analyte/concentration
from the file body (never the filename), and build_overlay_json turning a set
of measurements into an ordered, color-graded, legend-deduped figure.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "viewer"))

from plotting import build_overlay_json, _format_concentration  # noqa: E402

from biosensor.readers.ch_instruments import CHInstrumentsReader
from biosensor.schema import Measurement


def _chi_bytes(sample=None, analyte=None, conc=None):
    lines = [
        "CHI Electrochemical Workstation",
        "Instrument Model = CHI600E",
        "",
        "Cyclic Voltammetry",
    ]
    if sample is not None:
        lines.append(f"Sample ID = {sample}")
    if analyte is not None:
        lines.append(f"Analyte = {analyte}")
    if conc is not None:
        lines.append(f"Concentration (M) = {conc}")
    lines += [
        "Init E (V) = -0.5",
        "Scan Rate (V/s) = 0.05",
        "",
        "Potential/V, Current/A",
        "-0.50,1.0e-07",
        "0.00,5.0e-06",
        "0.50,1.0e-07",
    ]
    return ("\n".join(lines) + "\n").encode()


def _measure(sample, analyte, conc, unit="M"):
    return Measurement(
        potential_v=[-0.5, 0.0, 0.5],
        current_a=[1e-7, 5e-6, 1e-7],
        sample_id=sample,
        analyte_name=analyte,
        analyte_concentration=conc,
        concentration_unit=unit,
    )


# --- reader reads identity from content, not filename ---------------------

def test_ch_reader_reads_sample_identity_from_content():
    raw = _chi_bytes(sample="IL-6 dilution series", analyte="interleukin-6", conc="5e-12")
    # Filename deliberately carries no concentration: identity must come from body.
    m = CHInstrumentsReader().parse(raw, "scan_a.txt")
    assert m.sample_id == "IL-6 dilution series"
    assert m.analyte_name == "interleukin-6"
    assert m.analyte_concentration == 5e-12
    assert m.concentration_unit == "M"


def test_ch_reader_leaves_identity_none_when_absent():
    m = CHInstrumentsReader().parse(_chi_bytes(), "blank.txt")
    assert m.sample_id is None
    assert m.analyte_name is None
    assert m.analyte_concentration is None
    assert m.concentration_unit is None


def test_ch_reader_ignores_non_numeric_concentration():
    raw = _chi_bytes(sample="s", conc="not-a-number")
    m = CHInstrumentsReader().parse(raw, "x.txt")
    assert m.sample_id == "s"
    assert m.analyte_concentration is None
    assert m.concentration_unit is None


# --- overlay figure builder -----------------------------------------------

def test_overlay_orders_and_dedupes_legend_by_concentration():
    # Two replicates each at three concentrations, supplied out of order.
    ms = [
        _measure("s", "a", 5e-11),
        _measure("s", "a", 0.0),
        _measure("s", "a", 5e-12),
        _measure("s", "a", 5e-11),
        _measure("s", "a", 0.0),
        _measure("s", "a", 5e-12),
    ]
    fig = build_overlay_json(ms)
    assert fig is not None
    assert len(fig["data"]) == 6
    legend = [t["name"] for t in fig["data"] if t["showlegend"]]
    assert legend == ["0 M", "5 pM", "50 pM"]  # ascending, one entry per level


def test_overlay_none_when_fewer_than_two_concentrations():
    assert build_overlay_json([_measure("s", "a", 1e-3), _measure("s", "a", 1e-3)]) is None
    assert build_overlay_json([_measure("s", "a", None)]) is None
    assert build_overlay_json([]) is None


def test_overlay_ignores_curves_without_concentration():
    ms = [
        _measure("s", "a", 0.0),
        _measure("s", "a", 5e-12),
        _measure("s", "a", None),  # no concentration: excluded from the plot
    ]
    fig = build_overlay_json(ms)
    assert len(fig["data"]) == 2


def test_overlay_color_grades_low_to_high():
    fig = build_overlay_json([_measure("s", "a", 0.0), _measure("s", "a", 1e-10)])
    colors = [t["line"]["color"] for t in fig["data"]]
    # Lowest concentration takes the light anchor, highest the dark anchor.
    assert colors[0] == "rgb(166,217,255)"
    assert colors[-1] == "rgb(11,44,92)"


def test_format_concentration_scales_to_tidy_prefix():
    assert _format_concentration(5e-12, "M") == "5 pM"
    assert _format_concentration(1e-10, "M") == "100 pM"
    assert _format_concentration(1e-3, "M") == "1 mM"
    assert _format_concentration(0.0, "M") == "0 M"
    assert _format_concentration(2.5, "mg/mL") == "2.5 mg/mL"  # non-molar left as-is
