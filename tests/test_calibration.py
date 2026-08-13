"""Calibration inset: peak-current methods and the calibration figure builder.

Covers the two v1 peak-current definitions (raw max and linear pre-peak
baseline) and build_calibration_json, which turns a sample's files into a
peak-current-vs-concentration scatter with a linear fit.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "viewer"))

from analysis import METHODS, _linfit, linear_prepeak, raw_max  # noqa: E402
from plotting import build_calibration_json, _format_current  # noqa: E402

from biosensor.schema import Measurement


def _peak_curve(peak_current, baseline=1e-7, n=41):
    """A flat baseline with a single symmetric peak, like a real voltammogram.

    The leading points sit on the flat baseline, so a pre-peak baseline fit has
    something to lock onto (a pure triangle would have no flat region).
    """
    peak_idx = int(n * 0.6)
    half = max(3, int(n * 0.2))
    potential, current = [], []
    for i in range(n):
        potential.append(-0.5 + i * (1.0 / (n - 1)))
        d = abs(i - peak_idx)
        frac = (1 - d / half) if d <= half else 0.0
        current.append(baseline + frac * (peak_current - baseline))
    return potential, current


def _measure(peak_current, conc, baseline=1e-7):
    p, c = _peak_curve(peak_current, baseline)
    return Measurement(potential_v=p, current_a=c, analyte_concentration=conc,
                       concentration_unit="M")


# --- peak-current methods --------------------------------------------------

def test_raw_max_is_the_maximum_with_zero_baseline():
    m = _measure(peak_current=9e-6, conc=1e-10, baseline=2e-7)
    r = raw_max(m)
    assert r.ip == max(m.current_a) == 9e-6
    assert r.baseline_at_peak == 0.0
    assert r.method == "raw_max"


def test_linear_prepeak_subtracts_the_baseline():
    # Flat 2e-7 baseline, peak at 9e-6: pre-peak baseline is ~2e-7, so the
    # corrected ip is the peak minus that, well below the raw max.
    m = _measure(peak_current=9e-6, conc=1e-10, baseline=2e-7)
    r = linear_prepeak(m)
    assert r.peak_current == 9e-6
    assert abs(r.baseline_at_peak - 2e-7) < 5e-8
    assert r.ip < r.peak_current
    assert abs(r.ip - (9e-6 - 2e-7)) < 1e-7
    assert r.baseline_points is not None  # geometry available for drawing


def test_linear_prepeak_falls_back_to_raw_when_too_few_leading_points():
    # Peak at index 1 leaves fewer than 3 leading points to fit a baseline.
    m = Measurement(potential_v=[-0.5, -0.4, -0.3, -0.2],
                    current_a=[1e-7, 9e-6, 2e-6, 1e-6],
                    analyte_concentration=1e-9, concentration_unit="M")
    r = linear_prepeak(m)
    assert r.ip == 9e-6           # raw fallback
    assert r.baseline_at_peak == 0.0
    assert r.method == "linear_prepeak"


def test_linfit_recovers_a_known_line():
    slope, intercept, r2 = _linfit([0, 1, 2, 3], [1, 3, 5, 7])  # y = 2x + 1
    assert abs(slope - 2) < 1e-9
    assert abs(intercept - 1) < 1e-9
    assert abs(r2 - 1.0) < 1e-9


# --- calibration figure ----------------------------------------------------

def _series():
    # Peak current rising with concentration, two replicates each.
    conc_peak = [(0.0, 3e-7), (5e-12, 8e-7), (1e-11, 1.3e-6), (1e-10, 9e-6)]
    ms = []
    for conc, pk in conc_peak:
        ms.append(_measure(pk, conc))
        ms.append(_measure(pk * 1.02, conc))
    return ms


def test_calibration_has_a_point_per_file_and_a_fit():
    fig = build_calibration_json(_series(), "raw_max")
    assert fig is not None
    scatter, fit = fig["data"]
    assert len(scatter["x"]) == 8          # one point per file
    assert scatter["x"] == sorted(scatter["x"])  # ordered by concentration
    assert len(fit["x"]) == 2              # a straight fit line
    assert 0.0 <= fig["r2"] <= 1.0
    assert "R²" in fit["name"]


def test_calibration_none_when_fewer_than_two_concentrations():
    assert build_calibration_json([_measure(9e-6, 1e-10)], "raw_max") is None
    assert build_calibration_json([], "raw_max") is None


def test_calibration_ignores_measurements_without_concentration():
    ms = _series() + [_measure(5e-6, None)]
    fig = build_calibration_json(ms, "raw_max")
    assert len(fig["data"][0]["x"]) == 8   # the None-concentration file is skipped


def test_calibration_unknown_method_falls_back_to_raw_max():
    fig = build_calibration_json(_series(), "does_not_exist")
    assert fig["method"] == "raw_max"


def test_prepeak_ip_is_below_raw_ip_on_the_same_series():
    raw = build_calibration_json(_series(), "raw_max")
    pre = build_calibration_json(_series(), "linear_prepeak")
    # Baseline subtraction can only lower each point.
    assert all(p <= r + 1e-12 for p, r in zip(pre["data"][0]["y"], raw["data"][0]["y"]))


def test_methods_registry_has_the_v1_pair():
    assert list(METHODS) == ["raw_max", "linear_prepeak"]
    assert "not baseline-corrected" in METHODS["raw_max"]["label"]


def test_format_current_scales_to_prefix():
    assert _format_current(9e-6) == "9 µA"
    assert _format_current(2.5e-7) == "250 nA"
    assert _format_current(0.0) == "0 A"
