"""Generate a varied, realistic sample dataset for manually exercising the
viewer: batch loading, filters, the ledger view, and the sanity/mapping
flows. Synthetic (not real instrument exports), but shaped like an
immunosensor concentration series — peak height scales with concentration,
matching the PRD's target workflow.

Run: python scripts/generate_sample_data.py
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "sample_data"
OUT.mkdir(exist_ok=True)
random.seed(7)


def cv_sweep(low=-0.5, high=0.5, step=0.02):
    up = [round(low + i * step, 4) for i in range(int((high - low) / step) + 1)]
    down = list(reversed(up))
    return up + down[1:]


def peak_current(v, center, width, amp, base, noise=0.0):
    y = base + amp * math.exp(-((v - center) ** 2) / (2 * width**2))
    if noise:
        y += random.gauss(0, noise * amp)
    return max(y, 1e-9)


def write(name: str, lines: list[str]) -> None:
    (OUT / name).write_text("\n".join(lines) + "\n")
    print(f"wrote {name} ({len(lines)} lines)")


# ---------------------------------------------------------------- CH Instruments: IL6 concentration series
CONCENTRATIONS_PM = [0, 5, 10, 25, 50, 100]
for conc in CONCENTRATIONS_PM:
    amp = 2e-7 + conc * 9e-8  # peak height scales with concentration
    for rep in (1, 2):
        sweep = cv_sweep()
        rows = [(v, peak_current(v, 0.1, 0.06, amp, 1.5e-7, noise=0.03)) for v in sweep]
        lines = [
            "CHI Electrochemical Workstation",
            f"File: cv_il6_{conc:03d}pM_r{rep:02d}.bin",
            "Data Source: CHI600E Electrochemical Analyzer",
            "Instrument Model: CHI600E",
            "",
            "Cyclic Voltammetry",
            "",
            "Init E (V) = -0.5",
            "High E (V) = 0.5",
            "Low E (V) = -0.5",
            "Init P/N = P",
            "Scan Rate (V/s) = 0.05",
            "Segment = 2",
            "Sample Interval (V) = 0.02",
            "Quiet Time (sec) = 2",
            "Sensitivity (A/V) = 1e-05",
            "",
            "Potential/V, Current/A",
            "",
        ]
        lines += [f"{v:.4f},{i:.6e}" for v, i in rows]
        write(f"cv_il6_{conc:03d}pM_r{rep:02d}.txt", lines)

# ---------------------------------------------------------------- CH Instruments: blank + ferricyanide reference
for rep in (1, 2):
    sweep = cv_sweep()
    rows = [(v, peak_current(v, 0.1, 0.06, 1.5e-7, 1.5e-7, noise=0.05)) for v in sweep]
    lines = [
        "CHI Electrochemical Workstation",
        f"File: cv_blank_r{rep:02d}.bin",
        "Data Source: CHI600E Electrochemical Analyzer",
        "Instrument Model: CHI600E",
        "",
        "Cyclic Voltammetry",
        "",
        "Init E (V) = -0.5",
        "High E (V) = 0.5",
        "Low E (V) = -0.5",
        "Scan Rate (V/s) = 0.05",
        "Sensitivity (A/V) = 1e-05",
        "",
        "Potential/V, Current/A",
        "",
    ]
    lines += [f"{v:.4f},{i:.6e}" for v, i in rows]
    write(f"cv_blank_r{rep:02d}.txt", lines)

for rep in (1, 2):
    sweep = cv_sweep(-0.3, 0.6)
    rows = [(v, peak_current(v, 0.2, 0.04, 6e-6, 2e-7, noise=0.02)) for v in sweep]
    lines = [
        "CHI Electrochemical Workstation",
        f"File: cv_ferro_ref_r{rep:02d}.bin",
        "Data Source: CHI600E Electrochemical Analyzer",
        "Instrument Model: CHI600E",
        "",
        "Cyclic Voltammetry",
        "",
        "Init E (V) = -0.3",
        "High E (V) = 0.6",
        "Low E (V) = -0.3",
        "Scan Rate (V/s) = 0.1",
        "Sensitivity (A/V) = 1e-05",
        "",
        "Potential/V, Current/A",
        "",
    ]
    lines += [f"{v:.4f},{i:.6e}" for v, i in rows]
    write(f"cv_ferro_ref_r{rep:02d}.txt", lines)

# ---------------------------------------------------------------- Metrohm Nova: DPV, single sweep (flags "no return sweep")
for i, conc in enumerate((25, 50), start=1):
    sweep_up = cv_sweep(-0.4, 0.4)[: len(cv_sweep(-0.4, 0.4)) // 2 + 1]  # up-sweep only
    amp = 1.5e-7 + conc * 4e-8
    rows = [(v, peak_current(v, 0.05, 0.05, amp, 2e-7, noise=0.03)) for v in sweep_up]
    lines = [
        "Metrohm Autolab B.V.",
        "Nova 2.1 export",
        "",
        "WE(1).Potential (V);WE(1).Current (A);Scan",
    ]
    lines += [f"{v:.4f};{i_:.6e};1" for v, i_ in rows]
    write(f"dpv_ifn_{conc:03d}pM_r{i:02d}.csv", lines)

# ---------------------------------------------------------------- Metrohm Nova: full CV
for rep in (1, 2, 3):
    sweep = cv_sweep(-0.2, 0.5)
    rows = [(v, peak_current(v, 0.15, 0.05, 4e-6, 2e-7, noise=0.02)) for v in sweep]
    lines = [
        "Metrohm Autolab B.V.",
        "Nova 2.1 export",
        "",
        "WE(1).Potential (V);WE(1).Current (A);Scan",
    ]
    lines += [f"{v:.4f};{i:.6e};1" for v, i in rows]
    write(f"nova_cv_ab_{rep:02d}.csv", lines)

# ---------------------------------------------------------------- PalmSens .pssession
for label in ("a", "b", "c"):
    sweep = cv_sweep(-0.4, 0.4)
    amp = random.uniform(2e-6, 6e-6)
    rows = [(v, peak_current(v, 0.08, 0.05, amp, 1.5e-7, noise=0.03)) for v in sweep]
    doc = {
        "Measurements": [
            {
                "Title": "Cyclic Voltammetry",
                "Method": {"Name": "Cyclic Voltammetry", "Scanrate": 0.05},
                "DataSet": {
                    "Values": [
                        {"Type": "Potential", "DataValues": [{"V": v} for v, _ in rows]},
                        {"Type": "Current", "DataValues": [{"V": i} for _, i in rows]},
                    ]
                },
            }
        ]
    }
    (OUT / f"ps_cv_screen_{label}.pssession").write_text(json.dumps(doc))
    print(f"wrote ps_cv_screen_{label}.pssession")

# ---------------------------------------------------------------- Generic CSV, clean
sweep = cv_sweep(-0.4, 0.4)
rows = [(v, peak_current(v, 0.1, 0.05, 3e-6, 2e-7, noise=0.02)) for v in sweep]
lines = ["potential_v,current_a,sample_id,analyte_concentration,concentration_unit"]
lines += [f"{v:.4f},{i:.6e},sample_ext_01,75,pM" for v, i in rows]
write("generic_export_clean.csv", lines)

# ---------------------------------------------------------------- Generic CSV, wrong column order (flags "column inference failed")
lines = ["time_s,V_meas,I_meas,temp_c"]
sweep = cv_sweep(-0.3, 0.3)
for i, v in enumerate(sweep):
    lines.append(f"{i * 0.2:.1f},{v:.4f},0.000,22.4")  # current column is all zero
write("pilot_scan_raw.csv", lines)

# ---------------------------------------------------------------- Deliberately unrecognizable file (batch error path)
write("notes.txt", ["Lab notebook page 14", "Ran out of blocking buffer, remade fresh", "Ambient temp 21.8 C"])

print("\nDone. Load this folder from the viewer's 'Load a folder' button.")
