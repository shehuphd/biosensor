# Biosensor

A lightweight Python package with an attached local viewer that converts raw
electrochemical instrument exports into one tidy dataframe schema, and lets
you visually verify the parse before trusting the output.

Targets solo researchers and small labs working on immunosensor and
biosensor cyclic voltammetry (CV) / DPV / SWV data who need a fast, local
path from raw instrument export to usable data, without adopting an
institutional ELN.

## Supported formats (v1)

- CH Instruments text export
- Metrohm Nova (Autolab) text/CSV export
- PalmSens `.pssession` (best-effort — see `src/biosensor_io/readers/palmsens.py`)
- Generic delimited CSV, with header-based column inference

Format detection is content-based (file signature and header content), not
filename-extension based.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Library usage

```python
from biosensor_io import load, batch_load, to_dataframe

result = load("cv01.txt")
df = to_dataframe(result.measurement)
print(result.qc.sanity_status)  # "ok" | "flagged" | "failed"

batch = batch_load("data/2026-08-05-run/")
df = batch.to_dataframe()          # all files, one tidy frame
qc_df = batch.qc_dataframe()       # per-file sanity status
```

Every reader converts its instrument-specific format into a `Measurement`
(potential, current, scan rate, cycle number, technique, sample ID, analyte
concentration, and a flexible `technique_params` dict for things like SWV
frequency or DPV pulse width). QC state (`sanity_status`, review notes)
lives in a separate `QCRecord` so the sanity heuristic can evolve without
touching the measurement schema.

## Viewer

```bash
./launch.command
# or: source .venv/bin/activate && python viewer/app.py
```

Opens at `http://127.0.0.1:5050`. Three panes: file list on the left (live
filter, ok/flagged/failed tabs), the CV curve (Plotly, zoom/pan) with
Dataframe and Overlay tabs in the center, and a parse record — quality
check, instrument metadata, sample/concentration mapping — on the right.
Load a single file or an entire folder, correct a wrong column mapping
in-place (see a live preview before applying), override the quality flag
manually, and export any file or the whole batch as CSV. Light/dark theme
toggle in Settings.

Visual design follows `internal/design/` (Tree Design System tokens).

The viewer is local, single-user, in-memory only — state resets on
restart. This is intentional (see Non-goals below).

## Tracing

Action-level tracing via [traceact](https://github.com/traceact/traceact)
(file parse, batch upload, mapping correction, CSV export) writes to
`data/traces/traces.jsonl` for local debugging — not required to run the
app, and gitignored.

## Sanity-check heuristic (v1)

A simple curve-shape check, not anything trained: flags constant/flat
current or potential (near-certain wrong column mapping), non-finite
values, too few points, a single-direction sweep with no return cycle, and
the absence of any peak/inflection in the current trace. Manual override is
always available in the viewer.

## Security

The viewer accepts arbitrary uploaded files and treats them as untrusted
input:

- Format detection inspects file content, never trusts the extension alone
- Per-file byte and data-row limits bound parsing cost (see `readers/base.py`)
- Any parse failure — including malformed or adversarial files — degrades
  to a per-file error, never a server crash
- Filenames, sample IDs, and technique strings derived from file content
  are sanitized before display and CSV export (including a CSV-formula
  injection guard)
- No macro or script execution in any format reader

## Non-goals (v1)

Peak fitting, baseline correction, calibration curves, ML modeling,
multi-user access, authentication, or cloud deployment. Four format readers
is the v1 target, not exhaustive vendor coverage.

## Tests

```bash
source .venv/bin/activate
pytest
```

Fixtures in `tests/fixtures/` are synthetic (generated, not real instrument
exports) but shaped like each format's real structure, including one
unrecognizable file to exercise the error path.

## Project layout

```
src/biosensor_io/       # the library: schema, readers, core API, QC heuristic
viewer/                 # Flask + HTMX + Plotly local viewer
tests/                  # pytest suite + synthetic fixtures
internal/                # PRD and other planning docs (gitignored)
```

## Author

Built by [Mo Shehu](https://mohammedshehu.com).
