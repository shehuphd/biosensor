# Changelog

All notable changes to Biosensor, newest first. Versions follow semantic
versioning.

## 1.4.0 - 2026-08-16

Viewer workflow and chart refinements, plus a leaner install and a test gate on
releases. No breaking API changes; the `Measurement` schema is unchanged.

### Packaging
- `pip install biosensor` now installs only pandas. Flask and traceact were the
  viewer's dependencies, not the library's, and moved to a `viewer` extra
  (`pip install "biosensor[viewer]"`). The launchers install `.[dev,viewer]`.
- Tests run in CI on every push and pull request (Python 3.10 and 3.12), and the
  publish workflow now runs the suite before building, so a red suite blocks a
  release.

### Viewer
- One **Add data** button replaces the separate file and folder buttons: choose
  one file, several files, or a whole folder, or drag any of them onto the
  window. Biosensor routes each by content.
- **Curve** tab: a Baseline dropdown draws the chosen peak-current method on the
  curve (raw max, linear pre-peak, or the new linear post-peak baseline), marking
  the peak and the measured height (ip). When a baseline estimate lands outside a
  physical range, the curve says so and suggests another method rather than
  showing a wrong number silently.
- Hovering anywhere in a potential column reads out that point's potential and
  current, instead of only the peak.
- The Dataframe tab hides columns that are empty for the file (an optional field
  with no value), so an empty middle band no longer forces horizontal scrolling.
  The exported CSV still carries every column.
- Confirmations render as an in-app dialog instead of a bare browser popup. The
  batch-error panel is collapsible and dismissable, and its category filter
  appears only when the failures span more than one category.
- Chart toolbar: a snapshot button that saves a PNG and copies it to the
  clipboard, the active tool highlighted, tooltips on every button, the toolbar
  pinned to the top-left, and the Plotly logo removed.

### Analysis
- New `linear_postpeak` peak-current method: fits the post-peak tail and
  extrapolates the baseline back under the peak, the mirror of `linear_prepeak`.
  Offered on both the Curve tab and the calibration inset.

## 1.3.0 - 2026-08-13

Adds a calibration inset to the viewer's Overlay tab. No breaking API changes;
the `Measurement` schema is unchanged.

### Viewer
- Calibration inset: below the concentration overlay, a plot of peak current
  against concentration with one point per file and a linear fit reporting its
  R². It appears for the same samples the overlay does (two or more
  concentrations of one `sample_id` + `analyte_name`).
- A method dropdown selects how peak current is measured. Raw max (not
  baseline-corrected) is the default and makes no baseline assumption; linear
  baseline (pre-peak) fits a line to the pre-peak foot, extrapolates it under
  the peak, and subtracts it. Both are offered because baseline estimation is
  unsettled, so the researcher chooses the convention their reporting expects.
- Point hovers state the method and its numbers: the raw method labels itself
  uncorrected; the baseline method shows the peak, the baseline at the peak, and
  the corrected height. Switching methods redraws client-side with no reload.

## 1.2.0 - 2026-08-13

Adds the viewer's Overlay tab and reads sample identity from file content. No
breaking API changes; the `Measurement` schema is unchanged.

### Library
- The CH Instruments reader now reads sample identity from the file body:
  `Sample ID`, `Analyte`, and `Concentration (M)` metadata lines populate
  `sample_id`, `analyte_name`, `analyte_concentration`, and
  `concentration_unit`. These come from the file's contents, never its
  filename, so a renamed file keeps the correct values.

### Viewer
- Overlay tab: overlays every loaded file of the same sample on one plot,
  colored and ordered by concentration, for the immunosensor dose-response
  view. Files are grouped by `sample_id` and `analyte_name`, computed live
  from the loaded set, so correcting a sample or concentration under Sample
  mapping regroups the overlay. A sample with fewer than two concentrations
  shows a short empty state instead.
- Dataframe tab: an instant row search and a larger in-page preview (up to
  2,000 rows) with a running count; the CSV export still covers the full file.
- The open file is kept in the URL, so a reload reopens it and its parse
  record instead of dropping back to the empty state.
- The plot area is a bounded flex column, so the curve fills its space
  predictably and the column-mapping bar stays in view rather than being
  pushed below the fold on a tall window.
- The footer count of files needing a confirmed sample mapping is now a
  control: clicking it filters the list to exactly those files.
- The selected file stays highlighted, the Curve and Overlay plots render
  only once their tab is visible (so neither renders mis-sized in a hidden
  container), and the card labels share one type size.

### Sample data
- The CH Instruments sample files carry `Sample ID`, `Analyte`, and
  `Concentration (M)` lines, so the IL-6 series exercises the Overlay through
  the content-based path rather than any filename convention.

### Tests
- Overlay coverage added (`tests/test_overlay.py`): content-based sample
  reading, concentration ordering, legend de-duplication, and the
  fewer-than-two-concentrations case.

## 1.1.0 - 2026-08-13

A correctness, safety, and robustness pass. No API changes.

### Library
- Non-base units are now rejected instead of mis-scaled. A generic-CSV column
  labelled `Current (mA)`, `Voltage (mV)`, or BioLogic's `<I>/mA` is rejected
  with a reason rather than stored 1000x off. Previously only an unrecognized
  spelling was rejected while a recognized one silently mis-scaled. (Automatic
  unit conversion is still planned, not yet shipped.)
- `load()` checks file size against the byte ceiling with `stat()` before
  reading, so an oversized file in a batch folder is rejected without first
  being pulled into memory in full.
- PalmSens reader hardening: detection requires JSON content, never the
  `.pssession` extension on its own, so a misnamed CSV falls through to the
  generic reader; potential/current arrays of unequal length are rejected
  instead of silently truncated to the shorter; and a first measurement that
  is not an object degrades to a `ParseError` rather than an unhandled
  `AttributeError`.
- Metrohm Nova: removed a stray current-header alternative that matched `I /V`
  (current in volts, which no instrument produces).
- `batch_load` skips dotfiles (`.DS_Store`, `.gitkeep`), so a macOS folder no
  longer adds a spurious per-batch error.

### Viewer
- Localhost-only request guard: any non-localhost `Host` (DNS-rebinding) and
  any cross-origin form POST are refused, closing the widest opening in the
  stated trust boundary.
- Non-numeric column-mapping input returns a 400 instead of a 500 debugger
  page.
- The server runs with `debug=False`, so the double-click launcher no longer
  exposes the Werkzeug debugger and reloader on a tool that ingests untrusted
  files.
- `Cache-Control: no-store` on every response, so a restart (which clears the
  in-memory store) is never shadowed by a stale cached page.
- The CSV formula-injection guard now covers pandas 3 `str`-dtype text columns
  (including `source_filename`), which the previous object-only selector
  covered only through a deprecated compatibility shim.
- htmx 2.0.10, Plotly 3.7.0, and the IBM Plex fonts (SIL Open Font License
  1.1) are vendored into `viewer/static/vendor/` instead of loaded from a CDN.
  The viewer now runs fully offline with no third-party CDN in its supply
  chain, and no longer depends on a superseded htmx 1.x.
- The dataframe preview shows a missing optional field (`cycle_number`,
  `scan_rate_v_s`) as a blank cell, matching the exported CSV and the parse
  record, instead of the literal text "nan".
- The primary toolbar accent follows what's actionable: Upload carries it when
  no files are loaded (nothing to export yet), and it moves to Export once a
  file exists.

### Tooling
- Launchers rebuild an incomplete virtual environment, use `python -m pip` and
  `ensurepip`, and start the app with the venv interpreter directly instead of
  relying on a shell-activated PATH.
- Regression tests added for every fix above.

## 1.0.0 - 2026-08-12

First public release.

### Library
- `load`, `batch_load`, and `to_dataframe`, returning the `Measurement` /
  `QCRecord` schema and the `LoadResult` / `BatchLoadResult` result types.
- Four content-detected readers: CH Instruments, Metrohm Nova, PalmSens
  `.pssession`, and generic delimited CSV. The generic reader handles a named
  header, one or more metadata lines before the header, and headerless
  two-column files (column 1 = potential, column 2 = current). Values are read
  in base SI units; a column it can't read as potential/current is rejected,
  never guessed at.
- Curve-shape QC heuristic (`sanity_check`) with `ok` / `flagged` / `failed`
  states, tracked in a `QCRecord` separate from the measurement data so the
  heuristic can change without touching the schema.
- Structured batch errors: `batch_load` records a `BatchError`
  (`filename`, `message`, `category`) per failed file instead of aborting, with
  a `category` of `unsupported` / `parse` / `too_large` / `corrupt` /
  `unexpected`. `classify_error`, `ERROR_CATEGORIES`, and `FileTooLargeError`
  are exported alongside `ParseError` and `UnsupportedFormatError`.
- Per-file byte and data-row ceilings, content-based format detection, input
  sanitization, and a CSV formula-injection guard for untrusted uploads.
- Full type hints with a `py.typed` marker.

### Viewer
- Local Flask + HTMX + Plotly viewer: file list with filter and status tabs,
  CV curve with dataframe and overlay tabs, parse record, in-place column
  mapping correction with a live preview, manual QC override, single and batch
  CSV export, a ledger view, and a light/dark theme toggle.
- Batch errors are grouped by category with per-category filter chips. The
  displayed version reads from the package, so it can't drift.

### Tooling
- MIT `LICENSE`, `USAGE.md`, `ARCHITECTURE.md`, and this changelog.
- Synthetic sample dataset across all four formats, and a pytest suite with
  adversarial reader and viewer coverage.

By [Mo Shehu](https://mohammedshehu.com)
