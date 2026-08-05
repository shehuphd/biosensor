"""Build a Plotly figure spec (as a plain dict) for a Measurement.

Kept separate from app.py so it can be unit tested without spinning up
Flask.
"""

from __future__ import annotations

from biosensor_io.schema import Measurement


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
