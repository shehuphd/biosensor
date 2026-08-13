# Biosensor Usage

The full manual. For a one-minute overview and install, see
[README.md](https://github.com/shehuphd/biosensor/blob/main/README.md).

## Install

```bash
pip install biosensor
```

That wheel is the library only. The viewer, the double-click launchers, and
`sample_data/` ship in the repository, not on PyPI. For those, and for the test
suite, clone and install in place:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## See it work

Load one file. Format detection is content-based, so you don't pass a format
flag:

```python
import biosensor as bio

result = bio.load("sample_data/cv_il6_100pM_r01.txt")
print(result.measurement.instrument_source)  # ch_instruments
print(result.measurement.technique)          # Cyclic Voltammetry
print(result.measurement.n_points)           # 101
print(result.qc.sanity_status)               # ok

df = bio.to_dataframe(result.measurement)
print(df.shape)                              # (101, 14)
```

Load a whole folder. One bad file never aborts the batch:

```python
batch = bio.batch_load("sample_data/")
print(len(batch.results), "parsed,", len(batch.errors), "errors")
# 25 parsed, 2 errors

df = batch.to_dataframe()                     # every file, one tidy frame
qc = batch.qc_dataframe()                     # per-file sanity status
print(qc["sanity_status"].value_counts().to_dict())
# {'ok': 25, 'failed': 2}
```

The two errors are the deliberately-unparseable files in `sample_data/`,
included to exercise the batch error path.

## Public API

| Function | Returns | Purpose |
|---|---|---|
| `load(filepath)` | `LoadResult` | Parse one file, auto-detecting its format |
| `batch_load(directory)` | `BatchLoadResult` | Parse every file in a folder |
| `to_dataframe(measurement)` | `pandas.DataFrame` | Expand one `Measurement` to a long-form frame |

`LoadResult` holds `.measurement` (a `Measurement`) and `.qc` (a `QCRecord`).

`BatchLoadResult` holds `.results` (a list of `LoadResult`) and `.errors` (a
list of `BatchError`, each carrying `.filename`, `.message`, and a `.category`;
see [Errors](#errors)), plus two convenience methods:

| Method | Returns | Purpose |
|---|---|---|
| `.to_dataframe()` | `pandas.DataFrame` | Every parsed file concatenated into one frame |
| `.qc_dataframe()` | `pandas.DataFrame` | One row per file with its sanity status; failed files fold in |

## The Measurement schema

`to_dataframe` expands a `Measurement` to one row per data point. Every row
carries the file-level metadata repeated, so a concatenated batch frame stays
self-describing.

| Field | Type | Notes |
|---|---|---|
| `potential_v` | list[float] | Potential, volts |
| `current_a` | list[float] | Current, amps |
| `scan_rate_v_s` | float or None | Scan rate, V/s |
| `cycle_number` | list[int] or None | Per-point cycle index |
| `technique` | str or None | e.g. "Cyclic Voltammetry" |
| `sample_id` | str or None | Read from file content, or set in the viewer's Sample mapping |
| `analyte_name` | str or None | e.g. "interleukin-6", read from file content |
| `analyte_concentration` | float or None | Populated when the file content or the viewer's Sample mapping supplies it |
| `concentration_unit` | str or None | e.g. "M" |
| `timestamp` | datetime or None | Parsed from file metadata when present |
| `replicate_id` | str or None | e.g. "r01" |
| `instrument_source` | str | Which reader parsed it |
| `source_filename` | str | Original filename |
| `schema_version` | str | Currently "1.0" |

The dataframe has 14 columns, one per field above. `technique_params` is not
among them: it stays a dict on the `Measurement` (SWV frequency, DPV pulse
width, and a `_column_mapping` record) and isn't expanded into the long-form
frame.

`analyte_concentration`, `scan_rate_v_s`, and `cycle_number` are typed
`float64` in the dataframe, so a file missing one of them holds `NaN` in that
column rather than mixing dtypes across a batch.

## Supported formats

Detection inspects file content, never the extension alone.

| Reader | `instrument_source` | Format |
|---|---|---|
| CH Instruments | `ch_instruments` | Text export |
| Metrohm Nova (Autolab) | `metrohm_nova` | Text/CSV export |
| PalmSens | `palmsens` | `.pssession` (JSON), best-effort |
| Generic CSV | `generic_csv` | Delimited CSV with header-based column inference |

The PalmSens reader is lenient by design: it walks the parsed JSON for arrays
whose type label matches "potential"/"current" rather than assuming one exact
shape. Files from unusual PSTrace versions may parse better through the
generic CSV path (most PalmSens software can export CSV directly).

The generic CSV reader handles three shapes: a header row naming the columns,
one or more metadata lines before that header (the header is found by scanning
the first lines), and headerless files, where column 1 is read as potential
(V) and column 2 as current (A). Values are read in base SI units; a current or
potential column labelled in a non-base unit (for example `Current (mA)` or
`Voltage (mV)`, including BioLogic's `<I>/mA`) is rejected with a reason
rather than silently mis-scaled. Automatic unit conversion is planned, not yet
shipped.

## Quality check

Every parse runs a sanity heuristic and records the result in a `QCRecord`,
separate from the measurement data so the heuristic can change without
touching the schema.

| `sanity_status` | Meaning |
|---|---|
| `ok` | Curve shape looks like a normal sweep |
| `flagged` | Parsed, but something looks off (see `sanity_reason`) |
| `failed` | Almost certainly a bad parse (constant column, too few points, non-finite values) |
| `unreviewed` | Initial state before a check runs |

The heuristic (`heuristic_version` "0.1") is a curve-shape check, not a
trained model. It catches silent parse failures: a constant potential or
current column (a swapped or wrong column mapping), fewer than 5 points, NaN
or infinite values, a one-direction sweep where a cycle was expected, and the
absence of any peak or inflection in the current trace. It doesn't judge assay
quality. The viewer lets you override any status by hand.

## Errors

`load()` raises. `batch_load()` catches per file and records a `BatchError`
(`.filename`, `.message`, `.category`) in `.errors` instead of aborting, so one
bad file never stops the batch.

| Exception | Raised when |
|---|---|
| `UnsupportedFormatError` | No reader recognizes the file content |
| `ParseError` | A reader matched the format but couldn't parse the body |
| `FileTooLargeError` | The file exceeds the byte or data-row ceiling (a `ParseError` subclass) |

All three live in `biosensor.readers.base` and are re-exported from the top
level. Each batch error also carries a stable category, so a run's failures can
be grouped and filtered:

| Category | Meaning |
|---|---|
| `unsupported` | No reader recognized the file |
| `parse` | Recognized, but the body couldn't be parsed |
| `too_large` | Exceeds the byte or row ceiling |
| `corrupt` | Data failed schema validation |
| `unexpected` | Any other error (the batch still completes) |

```python
batch = bio.batch_load("data/")
for err in batch.errors:
    print(err.category, err.filename, err.message)
```

`classify_error(exc)` returns the category for an exception, and
`ERROR_CATEGORIES` lists them all. `batch.qc_dataframe()` includes an
`error_category` column (`None` for files that parsed).

## Safety limits

Readers treat every file as untrusted input:

| Limit | Value | Location |
|---|---|---|
| Max bytes read per file | 25 MB | `readers/base.py` |
| Max data rows parsed | 200,000 | `readers/base.py` |
| Dataframe rows shown in the viewer preview | 2,000 | `viewer/templates/partials/detail.html` |

The 2,000-row cap is a display limit for the Dataframe tab only, so a large
file's preview stays responsive; the row search covers those shown rows, and
the CSV export always writes every parsed row.

Detection is content-based, no reader executes embedded macros or scripts, and
any parse failure degrades to a per-file error rather than a crash.

## Viewer

The viewer is a local, single-user Flask app. State is in-memory and resets on
restart. Start it with the launcher for your platform, or manually:

```bash
source .venv/bin/activate && python viewer/app.py
```

It opens at `http://127.0.0.1:5050`. Load a single file or a folder, inspect
the CV curve and the parse record, correct a wrong column mapping in-place
with a live preview, override the quality flag, and export a single file or
the whole batch as CSV. CSV export defuses spreadsheet-formula injection in any
text field derived from file content.

The center pane has three tabs:

- **Curve**: the file's voltammogram (current vs potential), one trace per
  cycle.
- **Dataframe**: the parsed rows with an instant search box; the preview
  shows up to 2,000 rows in the page, and the CSV export covers the full file.
- **Overlay**: every loaded file that shares this file's sample, drawn on one
  plot, colored and ordered by concentration, for the dose-response view.
  Grouping is by `sample_id` and `analyte_name`, read from file content;
  correcting a sample or concentration under Sample mapping regroups it. A
  sample with fewer than two concentrations shows a short empty state.

The open file is kept in the URL, so reloading the page reopens it.

By [Mo Shehu](https://mohammedshehu.com)
