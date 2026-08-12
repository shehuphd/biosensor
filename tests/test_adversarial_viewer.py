"""Adversarial cases for the Flask viewer: untrusted filenames, injection
attempts against the two render surfaces (HTML and CSV), oversized
uploads, and malformed requests. Per CODING.md, every defense here
(secure_filename, the CSV-formula guard, MAX_CONTENT_LENGTH, Jinja
autoescape) gets a test that actually exercises the attack it exists for.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "viewer"))

import pytest

import app as viewer_app  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    viewer_app.app.config["TESTING"] = True
    viewer_app.STORE.clear()
    with viewer_app.app.test_client() as c:
        yield c
    viewer_app.STORE.clear()


def _upload(client, filename: str, content: bytes, field: str = "file"):
    return client.post(
        "/parse",
        data={"file": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


CHI_VALID = (
    b"CHI Electrochemical Workstation\n"
    b"Instrument Model: CHI600E\n"
    b"Potential/V, Current/A\n"
    b"-0.5,1e-7\n-0.4,1e-7\n-0.3,5e-6\n-0.2,1e-7\n-0.1,1e-7\n"
)


# ---------------------------------------------------------------- path traversal / filename injection

def test_path_traversal_filename_is_sanitized(client):
    resp = _upload(client, "../../../../etc/passwd_evil.txt", CHI_VALID)
    assert resp.status_code == 200
    assert len(viewer_app.STORE) == 1
    entry = next(iter(viewer_app.STORE.values()))
    stored_name = entry["result"].measurement.source_filename
    assert ".." not in stored_name
    assert "/" not in stored_name


def test_absolute_path_filename_is_sanitized(client):
    resp = _upload(client, "/etc/passwd", CHI_VALID)
    assert resp.status_code == 200
    entry = next(iter(viewer_app.STORE.values()))
    assert "/" not in entry["result"].measurement.source_filename


def test_null_byte_in_filename_does_not_crash(client):
    resp = _upload(client, "evil\x00.txt", CHI_VALID)
    assert resp.status_code == 200


# ---------------------------------------------------------------- XSS: filename and sample_id rendered into HTML

def test_script_tag_filename_is_escaped_in_rendered_html(client):
    # secure_filename() strips <>/ etc., but assert the actual HTML
    # response never contains a live <script> tag regardless of what
    # secure_filename does to the name.
    resp = _upload(client, "<script>alert(1)</script>.txt", CHI_VALID)
    assert resp.status_code == 200
    assert b"<script>alert(1)</script>" not in resp.data


def test_html_injection_via_sample_id_is_escaped(client):
    payload = "<img src=x onerror=alert(1)>"
    raw = f"potential_v,current_a,sample_id\n-0.1,1e-6,{payload}\n0.0,5e-6,{payload}\n0.1,1e-6,{payload}\n0.2,1e-6,{payload}\n0.3,1e-6,{payload}\n".encode()
    _upload(client, "inject.csv", raw)
    file_id = next(iter(viewer_app.STORE))
    resp = client.get(f"/file/{file_id}")
    assert b"<img src=x onerror=alert(1)>" not in resp.data
    assert b"&lt;img" in resp.data or b"onerror" not in resp.data


# ---------------------------------------------------------------- CSV formula injection on export

def test_csv_formula_injection_via_sample_id_is_defused(client):
    payload = "=cmd|'/c calc'!A1"
    raw = f"potential_v,current_a,sample_id\n-0.1,1e-6,{payload}\n0.0,5e-6,{payload}\n0.1,1e-6,{payload}\n0.2,1e-6,{payload}\n0.3,1e-6,{payload}\n".encode()
    _upload(client, "inject.csv", raw)
    file_id = next(iter(viewer_app.STORE))

    resp = client.get(f"/file/{file_id}/dataframe")
    csv_text = resp.data.decode()
    for line in csv_text.splitlines()[1:]:
        if not line.strip():
            continue
        # The sample_id field must not appear as a live formula in the
        # exported CSV: a leading "=" must be neutralized before it ever
        # reaches the file a researcher opens in Excel.
        assert "=cmd" not in line or "'=cmd" in line


def test_csv_formula_injection_at_symbol_and_plus_are_defused(client):
    import csv as csv_module

    for trigger in ("@SUM(1+1)", "+1+1"):
        viewer_app.STORE.clear()
        raw = f"potential_v,current_a,sample_id\n-0.1,1e-6,{trigger}\n0.0,5e-6,{trigger}\n0.1,1e-6,{trigger}\n0.2,1e-6,{trigger}\n0.3,1e-6,{trigger}\n".encode()
        _upload(client, "inject.csv", raw)
        file_id = next(iter(viewer_app.STORE))
        resp = client.get(f"/file/{file_id}/dataframe")
        rows = list(csv_module.reader(io.StringIO(resp.data.decode())))
        header, data_rows = rows[0], [r for r in rows[1:] if r]
        sample_id_idx = header.index("sample_id")
        assert data_rows, "expected at least one data row"
        for row in data_rows:
            cell = row[sample_id_idx]
            # A formula-trigger prefix must have been neutralized with a
            # leading apostrophe before reaching the CSV a researcher
            # opens in Excel.
            assert not cell.startswith(("=", "+", "@")) or cell.startswith("'")


# ---------------------------------------------------------------- oversized upload

def test_upload_over_max_content_length_is_rejected(client):
    huge = b"potential_v,current_a\n" + b"0.1,1e-6\n" * 5_000_000  # well over 30 MB
    resp = client.post(
        "/parse",
        data={"file": (io.BytesIO(huge), "huge.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413


# ---------------------------------------------------------------- malformed / hostile requests, never a 500

def test_unrecognized_file_reports_error_not_crash(client):
    resp = _upload(client, "notes.txt", b"just some lab notes, not instrument data")
    assert resp.status_code == 200
    assert len(viewer_app.STORE) == 0


def test_missing_file_field_handled_gracefully(client):
    resp = client.post("/parse", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_nonexistent_file_id_returns_404_not_500(client):
    for path in ["/file/does-not-exist", "/file/does-not-exist/dataframe", "/file/does-not-exist/mapping/edit"]:
        resp = client.get(path)
        assert resp.status_code == 404


def test_delete_nonexistent_file_id_is_a_no_op_not_error(client):
    resp = client.delete("/file/does-not-exist")
    assert resp.status_code == 200


def test_review_with_invalid_status_value_is_rejected(client):
    _upload(client, "chi.txt", CHI_VALID)
    file_id = next(iter(viewer_app.STORE))
    resp = client.post(f"/file/{file_id}/review", data={"sanity_status": "<script>evil</script>"})
    assert resp.status_code == 400


def test_mapping_with_non_numeric_concentration_is_rejected(client):
    _upload(client, "chi.txt", CHI_VALID)
    file_id = next(iter(viewer_app.STORE))
    resp = client.post(
        f"/file/{file_id}/mapping",
        data={"sample_id": "x", "analyte_concentration": "not-a-number", "concentration_unit": "nM"},
    )
    assert resp.status_code == 400


def test_mapping_edit_on_uncorrectable_format_is_rejected_not_crash(client):
    doc = (
        b'{"Measurements":[{"Method":{"Name":"CV"},"DataSet":{"Values":['
        b'{"Type":"Potential","DataValues":[{"V":-0.1},{"V":0.0},{"V":0.1},{"V":0.2},{"V":0.3}]},'
        b'{"Type":"Current","DataValues":[{"V":1e-6},{"V":5e-6},{"V":1e-6},{"V":1e-6},{"V":1e-6}]}'
        b"]}}]}"
    )
    _upload(client, "sample.pssession", doc)
    file_id = next(iter(viewer_app.STORE))
    resp = client.get(f"/file/{file_id}/mapping/edit")
    assert resp.status_code == 400


def test_mapping_apply_with_out_of_range_column_index_is_handled(client):
    _upload(client, "chi.txt", CHI_VALID)
    file_id = next(iter(viewer_app.STORE))
    resp = client.post(
        f"/file/{file_id}/mapping/apply",
        data={
            "potential_col": "99",
            "current_col": "100",
            "cycle_col": "none",
            "potential_unit": "V",
            "current_unit": "A",
            "origin": "panes",
        },
    )
    # No column has index 99/100 -> no rows parse -> the measurement is
    # left untouched (not corrupted, not a 500).
    assert resp.status_code in (200, 400)
    assert len(viewer_app.STORE) == 1


def test_batch_upload_with_no_files_is_handled(client):
    resp = client.post("/batch", data={}, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert len(viewer_app.STORE) == 0


# ---------------------------------------------------------------- long strings get bounded

def test_extremely_long_sample_id_is_truncated():
    long_value = viewer_app._sanitize_display("x" * 10_000)
    assert len(long_value) <= 500


def test_control_characters_stripped_from_display_strings():
    dirty = "sample\x00\x01\x02_id\x1b[31mred"
    cleaned = viewer_app._sanitize_display(dirty)
    assert "\x00" not in cleaned
    assert "\x1b" not in cleaned


# ---------------------------------------------------------------- batch errors are grouped by category

def test_batch_errors_render_grouped_by_category(client):
    files = [
        ("empty.csv", b""),                                  # unsupported
        ("people.csv", b"name,city\nAlice,Lagos\nBob,Accra\n"),  # unsupported
        ("truncated.pssession", b'{"Measurements": [{"DataSet": {"Val'),  # parse
    ]
    resp = client.post(
        "/batch",
        data={"files": [(io.BytesIO(content), name) for name, content in files]},
        content_type="multipart/form-data",
    )
    html = resp.get_data(as_text=True)
    assert 'class="flash-errors"' in html
    # filter chips carry the per-category counts
    assert "unsupported (2)" in html
    assert "parse (1)" in html
    # each failed file is listed with its category tag
    assert 'data-cat="unsupported"' in html and 'data-cat="parse"' in html
    assert "people.csv" in html and "truncated.pssession" in html
