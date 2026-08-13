"""Build a Plotly figure spec (as a plain dict) for a Measurement.

Kept separate from app.py so it can be unit tested without spinning up
Flask.
"""

from __future__ import annotations

from analysis import METHODS, _linfit
from biosensor.schema import Measurement


def _format_current(value: float) -> str:
    """Human label for a current, scaled to a tidy SI prefix."""
    x = abs(value)
    if x == 0:
        return "0 A"
    for factor, suffix in (
        (1.0, "A"),
        (1e-3, "mA"),
        (1e-6, "µA"),
        (1e-9, "nA"),
        (1e-12, "pA"),
    ):
        if x >= factor:
            return f"{value / factor:.3g} {suffix}"
    return f"{value:.3g} A"


def _format_concentration(value: float, unit: str | None) -> str:
    """Human label for a concentration, molar values scaled to a tidy prefix."""
    if unit and unit != "M":
        return f"{value:g} {unit}"
    if value == 0:
        return "0 M"
    for factor, suffix in (
        (1.0, "M"),
        (1e-3, "mM"),
        (1e-6, "µM"),
        (1e-9, "nM"),
        (1e-12, "pM"),
    ):
        if abs(value) >= factor:
            return f"{value / factor:g} {suffix}"
    return f"{value:g} M"


def _sequential_color(t: float) -> str:
    """Interpolate a low-to-high concentration color, light blue to deep navy."""
    lo = (166, 217, 255)
    hi = (11, 44, 92)
    r, g, b = (round(lo[i] + (hi[i] - lo[i]) * t) for i in range(3))
    return f"rgb({r},{g},{b})"


def build_overlay_json(measurements: list[Measurement]) -> dict | None:
    """Overlay curves of one sample across its concentration series.

    Returns ``None`` when fewer than two distinct concentrations are present,
    since there's nothing to compare; the caller shows an empty state instead.
    Curves are colored and ordered by concentration, with replicates of a
    concentration sharing one legend entry.
    """
    series = [m for m in measurements if m.analyte_concentration is not None]
    distinct = sorted({m.analyte_concentration for m in series})
    if len(distinct) < 2:
        return None

    n = len(distinct)
    series.sort(key=lambda m: m.analyte_concentration)
    traces = []
    seen: set[float] = set()
    for m in series:
        idx = distinct.index(m.analyte_concentration)
        t = idx / (n - 1)
        label = _format_concentration(m.analyte_concentration, m.concentration_unit)
        first = m.analyte_concentration not in seen
        seen.add(m.analyte_concentration)
        traces.append(
            {
                "x": m.potential_v,
                "y": m.current_a,
                "mode": "lines",
                "type": "scatter",
                "name": label,
                "legendgroup": label,
                "showlegend": first,
                "line": {"color": _sequential_color(t)},
            }
        )

    layout = {
        "xaxis": {"title": "Potential (V)"},
        "yaxis": {"title": "Current (A)"},
        "margin": {"t": 30, "r": 20, "b": 50, "l": 70},
        "hovermode": "closest",
        "legend": {"title": {"text": "Concentration"}},
    }
    return {"data": traces, "layout": layout}


def build_calibration_json(measurements: list[Measurement], method: str = "raw_max") -> dict | None:
    """Peak current vs concentration for one sample, under a chosen peak method.

    One point per file (x = concentration, y = peak current), colored to match
    the overlay, plus a linear fit and its R-squared. Returns ``None`` when
    fewer than two distinct concentrations are present, matching the overlay.
    Each point's hover states what was measured (raw peak, and for a baseline
    method the peak, baseline, and resulting ip), so the method is never hidden.
    """
    if method not in METHODS:
        method = "raw_max"
    fn = METHODS[method]["fn"]

    rows = []
    for m in measurements:
        if m.analyte_concentration is None:
            continue
        rows.append((m.analyte_concentration, fn(m), m))

    distinct = sorted({r[0] for r in rows})
    if len(distinct) < 2:
        return None

    rows.sort(key=lambda r: r[0])
    n = len(distinct)
    xs = [r[0] for r in rows]
    ys = [r[1].ip for r in rows]
    colors = [_sequential_color(distinct.index(r[0]) / (n - 1)) for r in rows]

    texts = []
    for conc, pr, m in rows:
        label = _format_concentration(conc, m.concentration_unit)
        if method == "raw_max":
            texts.append(
                f"{label}<br>peak current (raw max): {_format_current(pr.peak_current)}"
                f"<br>not baseline-corrected"
            )
        else:
            texts.append(
                f"{label}<br>peak: {_format_current(pr.peak_current)}"
                f"<br>baseline: {_format_current(pr.baseline_at_peak)}"
                f"<br>ip: {_format_current(pr.ip)}"
            )

    slope, intercept, r2 = _linfit(xs, ys)
    fit_x = [xs[0], xs[-1]]
    fit_y = [slope * fit_x[0] + intercept, slope * fit_x[1] + intercept]

    scatter = {
        "x": xs,
        "y": ys,
        "text": texts,
        "mode": "markers",
        "type": "scatter",
        "name": "peak current",
        "marker": {"color": colors, "size": 11, "line": {"color": "#3a3a3a", "width": 1}},
        "hovertemplate": "%{text}<extra></extra>",
    }
    fit = {
        "x": fit_x,
        "y": fit_y,
        "mode": "lines",
        "type": "scatter",
        "name": f"linear fit (R²={r2:.3f})",
        "line": {"color": "#8a8a8a", "dash": "dash"},
        "hovertemplate": (
            "linear fit, R²=%.3f<br>dose-response often saturates; "
            "treat this as a first approximation<extra></extra>" % r2
        ),
    }
    unit = next((m.concentration_unit for _, _, m in rows), None) or "M"
    layout = {
        "xaxis": {"title": f"Concentration ({unit})", "tickformat": ".2s"},
        "yaxis": {"title": "Peak current (A)", "tickformat": ".2s"},
        "margin": {"t": 30, "r": 20, "b": 50, "l": 70},
        "hovermode": "closest",
        "showlegend": True,
        "legend": {"orientation": "h", "y": -0.25},
    }
    return {"data": [scatter, fit], "layout": layout, "method": method, "r2": r2}


def build_plot_json(m: Measurement) -> dict:
    if m.cycle_number:
        cycles: dict[int, dict[str, list[float]]] = {}
        for p, c, cyc in zip(m.potential_v, m.current_a, m.cycle_number):
            bucket = cycles.setdefault(cyc, {"x": [], "y": []})
            bucket["x"].append(p)
            bucket["y"].append(c)
        traces = [
            {
                "x": data["x"],
                "y": data["y"],
                "mode": "lines",
                "type": "scatter",
                "name": f"Cycle {cyc}",
            }
            for cyc, data in sorted(cycles.items())
        ]
    else:
        traces = [
            {
                "x": m.potential_v,
                "y": m.current_a,
                "mode": "lines",
                "type": "scatter",
                "name": m.source_filename,
            }
        ]

    layout = {
        "xaxis": {"title": "Potential (V)"},
        "yaxis": {"title": "Current (A)"},
        "margin": {"t": 30, "r": 20, "b": 50, "l": 70},
        "hovermode": "closest",
    }

    return {"data": traces, "layout": layout}
