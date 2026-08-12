# Changelog

All notable changes to Biosensor, newest first. Versions follow semantic
versioning.

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

Built by Mo Shehu, mohammedshehu.com
