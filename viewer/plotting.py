"""Build a Plotly figure spec (as a plain dict) for a Measurement.

Kept separate from app.py so it can be unit tested without spinning up
Flask.
"""

from __future__ import annotations

from biosensor.schema import Measurement


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
