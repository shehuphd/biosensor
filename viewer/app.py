"""Biosensor viewer: local Flask + HTMX app for parsing and sanity-checking
electrochemical exports.

Single-user, local-only (no auth, no cloud deployment). State lives in an
in-memory store for the life of the process.

Visual design follows the Tree Design System tokens: the in-app copy label
is "Quality check" throughout, though the underlying field name
(`qc.sanity_status`) is unchanged.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import replace
from pathlib import Path

from flask import Flask, Response, render_template, request
from werkzeug.utils import secure_filename

import traceact
from biosensor import __version__ as biosensor_version
from biosensor.core import LoadResult, to_dataframe
from biosensor.qc import sanity_check
from biosensor.readers.base import ParseError, UnsupportedFormatError, classify_error
from biosensor.readers.detect import detect_reader
from mapping import (
    CORRECTABLE_SOURCES,
    CURRENT_UNITS,
    POTENTIAL_UNITS,
    preview_svg_path,
    read_raw_table,
    reparse_with_manual_mapping,
)
from plotting import build_plot_json
from preview import build_dataframe_preview

_TRACES_DIR = Path(__file__).resolve().parent.parent / "data" / "traces"
_TRACES_DIR.mkdir(parents=True, exist_ok=True)
traceact.configure(
    project="biosensor",
    sinks=[traceact.JsonlSink(str(_TRACES_DIR / "traces.jsonl"))],
)

app = Flask(__name__)
app.wsgi_app = traceact.TraceActMiddleware(app.wsgi_app)
# Upload size cap: bound total request size before per-file parsing limits
# even come into play (security consideration: untrusted uploads).
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024  # 30 MB per request
app.jinja_env.globals["app_version"] = biosensor_version
app.jinja_env.globals["plot_json"] = build_plot_json
app.jinja_env.globals["dataframe_preview"] = build_dataframe_preview

_DETECTION_LABELS = {
    "ch_instruments": "header signature",
    "metrohm_nova": "header signature",
    "generic_csv": "header signature",
    "palmsens": "content signature",
}
app.jinja_env.globals["detection_label"] = lambda source: _DETECTION_LABELS.get(source, "content signature")
app.jinja_env.globals["visible_params"] = lambda params: {
    k: v for k, v in (params or {}).items() if not k.startswith("_")
}

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _asset_version() -> str:
    """Cache-bust static/style.css by its mtime, so a stale browser cache
    of an old build never masks a CSS fix behind a hard-refresh."""
    try:
        return str(int((_STATIC_DIR / "style.css").stat().st_mtime))
    except OSError:
        return "0"


app.jinja_env.globals["asset_version"] = _asset_version
app.jinja_env.globals["sparkline_path"] = lambda m: preview_svg_path(m, width=90, height=28)

# file_id -> {"raw": bytes, "result": LoadResult, "mapping_confirmed": bool}.
# In-memory, single-process, local-only; resets on restart by design.
STORE: dict[str, dict] = {}


def _sanitize_display(value: str | None) -> str | None:
    """Defense-in-depth escaping for file-content-derived strings.

    Jinja2 autoescapes template output already; this additionally strips
    the raw string so nothing control-character-laden ends up in
    filenames, sample IDs, or error messages that flow into JSON/CSV too.
    """
    if value is None:
        return None
    cleaned = "".join(ch for ch in value if ch.isprintable())
    return cleaned[:500]


def _sanitize_measurement(measurement):
    measurement.sample_id = _sanitize_display(measurement.sample_id)
    measurement.analyte_name = _sanitize_display(measurement.analyte_name)
    measurement.technique = _sanitize_display(measurement.technique)
    return measurement


@traceact.traced_action(action="file.parse", kind="file", capture_inputs=False)
def _parse_upload(file_storage) -> tuple[str, bytes, LoadResult] | tuple[str, None, dict]:
    filename = secure_filename(file_storage.filename or "upload")
    raw = file_storage.read()
    try:
        reader = detect_reader(raw, filename)
        measurement = _sanitize_measurement(reader.parse(raw, filename))
        qc = sanity_check(measurement)
        return filename, raw, LoadResult(measurement=measurement, qc=qc)
    except (ParseError, UnsupportedFormatError, ValueError) as e:
        return filename, None, {"message": str(e), "category": classify_error(e)}
    except Exception as e:
        # Untrusted input: any other parse-time failure (e.g. a
        # pathologically nested JSON payload) is reported as a failed parse,
        # never a 500 that leaks a stack trace. The exception type is safe to
        # name; the raw message is withheld in case it echoes file content.
        return filename, None, {
            "message": f"file could not be parsed (unexpected {type(e).__name__})",
            "category": "unexpected",
        }


def _error_entry(filename: str, outcome: dict) -> dict:
    return {"filename": filename, "message": outcome["message"], "category": outcome["category"]}


def _store(file_id: str, raw: bytes, result: LoadResult) -> None:
    STORE[file_id] = {"raw": raw, "result": result, "mapping_confirmed": False}


def _stats() -> dict:
    results = [entry["result"] for entry in STORE.values()]
    ok = sum(1 for r in results if r.qc.sanity_status == "ok")
    flagged = sum(1 for r in results if r.qc.sanity_status == "flagged")
    failed = sum(1 for r in results if r.qc.sanity_status == "failed")
    formats = {r.measurement.instrument_source for r in results}
    rows = sum(r.measurement.n_points for r in results)
    unconfirmed = sum(1 for e in STORE.values() if not e["mapping_confirmed"])
    return {
        "files": len(STORE),
        "formats": len(formats),
        "rows": rows,
        "ok": ok,
        "flagged": flagged,
        "failed": failed,
        "unconfirmed": unconfirmed,
    }


@app.route("/")
def index():
    return render_template("index.html", store=STORE, stats=_stats())


def _upload_response_template() -> str:
    return "partials/ledger_table.html" if request.form.get("view") == "ledger" else "partials/table.html"


@app.route("/parse", methods=["POST"])
def parse_single():
    file_storage = request.files.get("file")
    if file_storage is None:
        return render_template(_upload_response_template(), store=STORE, stats=_stats()), 400

    filename, raw, outcome = _parse_upload(file_storage)
    if raw is None:
        return render_template(
            _upload_response_template(),
            store=STORE,
            stats=_stats(),
            flash_errors=[_error_entry(filename, outcome)],
        )

    file_id = uuid.uuid4().hex
    _store(file_id, raw, outcome)
    return render_template(_upload_response_template(), store=STORE, stats=_stats(), selected_id=file_id)


@app.route("/batch", methods=["POST"])
@traceact.traced_action(action="batch.upload", kind="app", capture_inputs=False)
def batch_upload():
    files = request.files.getlist("files")
    errors = []
    for file_storage in files:
        if not file_storage or not file_storage.filename:
            continue
        filename, raw, outcome = _parse_upload(file_storage)
        if raw is None:
            errors.append(_error_entry(filename, outcome))
            continue
        file_id = uuid.uuid4().hex
        _store(file_id, raw, outcome)

    return render_template(
        _upload_response_template(), store=STORE, stats=_stats(), flash_errors=errors or None
    )


@app.route("/file/<file_id>")
def file_detail(file_id: str):
    entry = STORE.get(file_id)
    if entry is None:
        return "<p class='error'>File not found (was it cleared by a server restart?)</p>", 404
    correctable = entry["result"].measurement.instrument_source in CORRECTABLE_SOURCES
    return render_template(
        "partials/detail.html",
        file_id=file_id,
        entry=entry,
        result=entry["result"],
        correctable=correctable,
    )


@app.route("/file/<file_id>/mapping", methods=["POST"])
def update_mapping(file_id: str):
    entry = STORE.get(file_id)
    if entry is None:
        return "<p class='error'>File not found</p>", 404

    m = entry["result"].measurement
    sample_id = _sanitize_display(request.form.get("sample_id", "").strip() or None)
    concentration_raw = request.form.get("analyte_concentration", "").strip()
    unit = _sanitize_display(request.form.get("concentration_unit", "").strip() or None)

    concentration = None
    if concentration_raw:
        try:
            concentration = float(concentration_raw)
        except ValueError:
            return (
                render_template(
                    "partials/detail.html",
                    file_id=file_id,
                    entry=entry,
                    result=entry["result"],
                    correctable=m.instrument_source in CORRECTABLE_SOURCES,
                    mapping_error="Concentration must be numeric.",
                ),
                400,
            )

    updated = replace(
        m,
        sample_id=sample_id,
        analyte_concentration=concentration,
        concentration_unit=unit,
    )
    entry["result"] = LoadResult(measurement=updated, qc=entry["result"].qc)
    entry["mapping_confirmed"] = True
    return render_template(
        "partials/detail.html",
        file_id=file_id,
        entry=entry,
        result=entry["result"],
        correctable=updated.instrument_source in CORRECTABLE_SOURCES,
        stats_oob=True,
        stats=_stats(),
    )


@app.route("/file/<file_id>/review", methods=["POST"])
def review_override(file_id: str):
    entry = STORE.get(file_id)
    if entry is None:
        return "<p class='error'>File not found</p>", 404

    status = request.form.get("sanity_status", "").strip()
    if status not in ("ok", "flagged", "failed"):
        return "<p class='error'>Invalid status</p>", 400

    reviewer = _sanitize_display(request.form.get("reviewed_by", "").strip() or "manual")
    updated_qc = replace(entry["result"].qc, sanity_status=status, reviewed_by=reviewer)
    entry["result"] = LoadResult(measurement=entry["result"].measurement, qc=updated_qc)
    return render_template(
        "partials/detail.html",
        file_id=file_id,
        entry=entry,
        result=entry["result"],
        correctable=entry["result"].measurement.instrument_source in CORRECTABLE_SOURCES,
        stats_oob=True,
        stats=_stats(),
    )


@app.route("/file/<file_id>", methods=["DELETE"])
@traceact.traced_action(action="file.remove", kind="app", capture_inputs=["file_id"])
def delete_file(file_id: str):
    STORE.pop(file_id, None)
    return render_template("partials/table.html", store=STORE, stats=_stats())


# ---------------------------------------------------------------- column mapping correction

_COL_INDEX_RE = re.compile(r"col (\d+)")


def _guess_col_index(mapping: dict | None, field: str, default: int) -> int:
    if not mapping or field not in mapping:
        return default
    match = _COL_INDEX_RE.search(mapping[field])
    return int(match.group(1)) - 1 if match else default


@app.route("/file/<file_id>/mapping/edit")
def edit_mapping(file_id: str):
    entry = STORE.get(file_id)
    if entry is None:
        return "<p class='error'>File not found</p>", 404
    m = entry["result"].measurement
    if m.instrument_source not in CORRECTABLE_SOURCES:
        return "<p class='error'>This format has no delimited columns to remap.</p>", 400

    table = read_raw_table(entry["raw"], m.source_filename, m.instrument_source)
    existing_mapping = (m.technique_params or {}).get("_column_mapping")
    selected = {
        "potential_col": _guess_col_index(existing_mapping, "potential_v", 0),
        "current_col": _guess_col_index(existing_mapping, "current_a", 1),
        "cycle_col": "none",
        "potential_unit": "V",
        "current_unit": "A",
    }
    other_count = sum(
        1 for fid, e in STORE.items()
        if fid != file_id and e["result"].measurement.instrument_source == m.instrument_source
    )
    return render_template(
        "partials/mapping_modal.html",
        file_id=file_id,
        filename=m.source_filename,
        instrument_source=m.instrument_source,
        table=table,
        potential_units=POTENTIAL_UNITS,
        current_units=CURRENT_UNITS,
        qc=entry["result"].qc,
        preview_path=None,
        selected=selected,
        other_count=other_count,
        origin=request.args.get("origin", "panes"),
    )


@app.route("/file/<file_id>/mapping/preview", methods=["POST"])
def preview_mapping(file_id: str):
    entry = STORE.get(file_id)
    if entry is None:
        return "<p class='error'>File not found</p>", 404
    m = entry["result"].measurement
    table = read_raw_table(entry["raw"], m.source_filename, m.instrument_source)

    pot_col = int(request.form.get("potential_col", 0))
    cur_col = int(request.form.get("current_col", 1))
    cycle_raw = request.form.get("cycle_col", "none")
    cycle_col = None if cycle_raw == "none" else int(cycle_raw)
    pot_unit = request.form.get("potential_unit", "V")
    cur_unit = request.form.get("current_unit", "A")

    preview_path = None
    would_pass = False
    try:
        preview_measurement = reparse_with_manual_mapping(
            entry["raw"], m.source_filename, m.instrument_source,
            pot_col, cur_col, cycle_col, pot_unit, cur_unit,
        )
        preview_path = preview_svg_path(preview_measurement)
        would_pass = sanity_check(preview_measurement).sanity_status == "ok"
    except (ParseError, ValueError):
        preview_path = None

    return render_template(
        "partials/mapping_modal.html",
        file_id=file_id,
        filename=m.source_filename,
        instrument_source=m.instrument_source,
        table=table,
        potential_units=POTENTIAL_UNITS,
        current_units=CURRENT_UNITS,
        qc=entry["result"].qc,
        preview_path=preview_path,
        would_pass=would_pass,
        selected={
            "potential_col": pot_col, "current_col": cur_col, "cycle_col": cycle_raw,
            "potential_unit": pot_unit, "current_unit": cur_unit,
        },
        other_count=sum(
            1 for fid, e in STORE.items()
            if fid != file_id and e["result"].measurement.instrument_source == m.instrument_source
        ),
        origin=request.form.get("origin", "panes"),
    )


@app.route("/file/<file_id>/mapping/apply", methods=["POST"])
@traceact.traced_action(action="mapping.correct", kind="app", capture_inputs=["file_id"])
def apply_mapping(file_id: str):
    entry = STORE.get(file_id)
    if entry is None:
        return "<p class='error'>File not found</p>", 404
    m = entry["result"].measurement

    pot_col = int(request.form.get("potential_col", 0))
    cur_col = int(request.form.get("current_col", 1))
    cycle_raw = request.form.get("cycle_col", "none")
    cycle_col = None if cycle_raw == "none" else int(cycle_raw)
    pot_unit = request.form.get("potential_unit", "V")
    cur_unit = request.form.get("current_unit", "A")
    apply_to_batch = request.form.get("apply_to_batch") == "on"

    targets = [file_id]
    if apply_to_batch:
        targets += [
            fid for fid, e in STORE.items()
            if fid != file_id and e["result"].measurement.instrument_source == m.instrument_source
        ]

    for fid in targets:
        target_entry = STORE.get(fid)
        if target_entry is None:
            continue
        target_m = target_entry["result"].measurement
        try:
            new_measurement = reparse_with_manual_mapping(
                target_entry["raw"], target_m.source_filename, target_m.instrument_source,
                pot_col, cur_col, cycle_col, pot_unit, cur_unit,
            )
        except ParseError:
            continue
        new_measurement = _sanitize_measurement(new_measurement)
        qc = sanity_check(new_measurement)
        target_entry["result"] = LoadResult(measurement=new_measurement, qc=qc)

    entry = STORE[file_id]
    if request.form.get("origin") == "ledger":
        return render_template(
            "partials/ledger_mapping_apply_result.html",
            file_id=file_id,
            entry=entry,
            result=entry["result"],
            correctable=entry["result"].measurement.instrument_source in CORRECTABLE_SOURCES,
            stats=_stats(),
        )
    return render_template(
        "partials/mapping_apply_result.html",
        store=STORE,
        stats=_stats(),
        selected_id=file_id,
        file_id=file_id,
        entry=entry,
        result=entry["result"],
        correctable=entry["result"].measurement.instrument_source in CORRECTABLE_SOURCES,
        plot_oob=True,
    )


def _csv_response(df, filename: str) -> Response:
    buffer = io.StringIO()
    _defuse_csv_formulas(df).to_csv(buffer, index=False, quoting=csv.QUOTE_MINIMAL)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _defuse_csv_formulas(df):
    """Prefix any string cell that could be read as a spreadsheet formula.

    Sample IDs, filenames, and technique strings all originate from
    uploaded file content, so any of them could smuggle a formula
    (e.g. "=CMD(...)") into a CSV a researcher later opens in Excel.
    """
    df = df.copy()
    for column in df.select_dtypes(include=["object"]).columns:
        df[column] = df[column].map(
            lambda v: ("'" + v) if isinstance(v, str) and v.startswith(_FORMULA_TRIGGER_CHARS) else v
        )
    return df


@app.route("/dataframe")
@traceact.traced_action(action="export.csv", kind="file", operation="write", target="batch", capture_inputs=False)
def export_all():
    import pandas as pd

    frames = [to_dataframe(e["result"].measurement) for e in STORE.values()]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return _csv_response(df, "biosensor_batch.csv")


@app.route("/file/<file_id>/dataframe")
@traceact.traced_action(action="export.csv", kind="file", operation="write", target="single", capture_inputs=["file_id"])
def export_one(file_id: str):
    entry = STORE.get(file_id)
    if entry is None:
        return "File not found", 404
    df = to_dataframe(entry["result"].measurement)
    safe_name = secure_filename(entry["result"].measurement.source_filename) or file_id
    return _csv_response(df, f"{safe_name}.csv")


@app.route("/ledger")
def ledger():
    return render_template("ledger.html", store=STORE, stats=_stats())


@app.route("/ledger/file/<file_id>")
def ledger_file_detail(file_id: str):
    entry = STORE.get(file_id)
    if entry is None:
        return "<p class='error'>File not found (was it cleared by a server restart?)</p>", 404
    correctable = entry["result"].measurement.instrument_source in CORRECTABLE_SOURCES
    return render_template(
        "partials/ledger_expand.html",
        file_id=file_id,
        entry=entry,
        result=entry["result"],
        correctable=correctable,
        stats=_stats(),
    )


def main():
    app.run(host="127.0.0.1", port=5050, debug=True)


if __name__ == "__main__":
    main()
