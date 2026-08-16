"""Peak-current extraction for the calibration inset.

A calibration curve plots each measurement's peak current against its
concentration. "Peak current" is not a single number. The literature
convention for quantitation is the current measured above an extrapolated
baseline (the Randles-Sevcik quantity); the raw maximum instead includes the
capacitive background. Baseline estimation is a hard, unsettled problem, so
rather than pick one method silently, the viewer exposes several labeled
methods and lets the researcher choose. This module holds the methods; the
viewer renders and switches them.

Kept separate from plotting so the peak logic can be unit-tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from biosensor.schema import Measurement


@dataclass
class PeakResult:
    ip: float                      # peak current used for the calibration point (A)
    peak_current: float            # raw current at the peak (A)
    peak_potential: float          # potential at the peak (V)
    baseline_at_peak: float        # baseline current under the peak (A); 0 for raw max
    method: str
    # (x0, y0, x1, y1) baseline segment for drawing on the curve, when applicable
    baseline_points: Optional[tuple] = None


def _argmax(values: list[float]) -> int:
    return max(range(len(values)), key=values.__getitem__)


def _linfit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Ordinary least squares. Returns (slope, intercept, r_squared)."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0, 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, 0.0
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, intercept, r2


def raw_max(m: Measurement) -> PeakResult:
    """The uncorrected maximum current. Includes the capacitive background."""
    i = _argmax(m.current_a)
    return PeakResult(
        ip=m.current_a[i],
        peak_current=m.current_a[i],
        peak_potential=m.potential_v[i],
        baseline_at_peak=0.0,
        method="raw_max",
    )


def linear_prepeak(m: Measurement) -> PeakResult:
    """Peak height above a baseline extrapolated from the pre-peak foot.

    Fits a line through the leading points before the peak and extrapolates it
    under the peak; the peak current is the height above that line. This is the
    standard tangent-baseline convention. It falls back to the raw maximum when
    there aren't enough leading points to fit a baseline.
    """
    cur, pot = m.current_a, m.potential_v
    i = _argmax(cur)
    if i < 3:
        r = raw_max(m)
        r.method = "linear_prepeak"
        return r
    k = max(3, i // 5)  # the first ~20% of the pre-peak points, at least 3
    xs = pot[:k]
    ys = cur[:k]
    slope, intercept, _ = _linfit(xs, ys)
    baseline_at_peak = slope * pot[i] + intercept
    return PeakResult(
        ip=cur[i] - baseline_at_peak,
        peak_current=cur[i],
        peak_potential=pot[i],
        baseline_at_peak=baseline_at_peak,
        method="linear_prepeak",
        baseline_points=(pot[0], slope * pot[0] + intercept, pot[i], baseline_at_peak),
    )


def linear_postpeak(m: Measurement) -> PeakResult:
    """Peak height above a baseline extrapolated from the post-peak tail.

    The mirror of ``linear_prepeak``: fits a line through the trailing points
    after the peak and extrapolates it back under the peak; the peak current is
    the height above that line. This is the other standard tangent-baseline
    convention. It falls back to the raw maximum when there aren't enough
    trailing points to fit a baseline.
    """
    cur, pot = m.current_a, m.potential_v
    i = _argmax(cur)
    trailing = len(cur) - 1 - i
    if trailing < 3:
        r = raw_max(m)
        r.method = "linear_postpeak"
        return r
    k = max(3, trailing // 5)  # the last ~20% of the post-peak points, at least 3
    xs = pot[-k:]
    ys = cur[-k:]
    slope, intercept, _ = _linfit(xs, ys)
    baseline_at_peak = slope * pot[i] + intercept
    return PeakResult(
        ip=cur[i] - baseline_at_peak,
        peak_current=cur[i],
        peak_potential=pot[i],
        baseline_at_peak=baseline_at_peak,
        method="linear_postpeak",
        baseline_points=(pot[i], baseline_at_peak, pot[-1], slope * pot[-1] + intercept),
    )


# Registry, in display order. The label states exactly what the method measures.
METHODS: dict[str, dict] = {
    "raw_max": {"label": "Raw max (not baseline-corrected)", "fn": raw_max},
    "linear_prepeak": {"label": "Linear baseline (pre-peak)", "fn": linear_prepeak},
    "linear_postpeak": {"label": "Linear baseline (post-peak)", "fn": linear_postpeak},
}
