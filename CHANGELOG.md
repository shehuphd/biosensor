# Changelog

All notable changes to Biosensor, newest first. Versions follow semantic
versioning.

## 1.0.0 — 2026-08-12

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

Built by Mo Shehu — mohammedshehu.com
