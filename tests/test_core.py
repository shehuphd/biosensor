from pathlib import Path

import pandas as pd
import pytest

from biosensor.core import batch_load, load, to_dataframe
from biosensor.readers.base import FileTooLargeError

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_single_file():
    result = load(FIXTURES / "chi_sample.txt")
    assert result.measurement.n_points == 41
    assert result.qc.sanity_status in ("ok", "flagged", "failed")


def test_to_dataframe_shape():
    result = load(FIXTURES / "generic_sample.csv")
    df = to_dataframe(result.measurement)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == result.measurement.n_points
    assert {"potential_v", "current_a", "sample_id", "instrument_source"}.issubset(df.columns)


def test_batch_load_mixed_folder():
    batch = batch_load(FIXTURES)
    # 4 good formats parse; bad_sample.txt fails
    assert len(batch.results) == 4
    assert len(batch.errors) == 1
    assert batch.errors[0].filename == "bad_sample.txt"
    assert batch.errors[0].category in ("unsupported", "parse", "corrupt", "unexpected")

    df = batch.to_dataframe()
    assert len(df) == sum(r.measurement.n_points for r in batch.results)

    qc_df = batch.qc_dataframe()
    assert len(qc_df) == 5  # 4 parsed + 1 error row
    assert (qc_df["sanity_status"] == "failed").sum() >= 1
    # error rows carry the category; parsed rows leave it blank
    assert "error_category" in qc_df.columns
    assert qc_df.loc[qc_df["filename"] == "bad_sample.txt", "error_category"].notna().all()


def test_batch_load_skips_dotfiles(tmp_path):
    # A macOS folder brings a .DS_Store; it must not add an error to the batch.
    (tmp_path / ".DS_Store").write_bytes(b"\x00\x01junk")
    (tmp_path / ".gitkeep").write_text("")
    (tmp_path / "cv.csv").write_text(
        "Potential (V),Current (A)\n" + "\n".join(f"{-0.3 + 0.01*i:.3f},{i*1e-7:.2e}" for i in range(20)) + "\n"
    )
    batch = batch_load(tmp_path)
    assert len(batch.results) == 1
    assert batch.errors == []


def test_load_rejects_oversized_file_by_stat(tmp_path, monkeypatch):
    # The size ceiling is checked against stat() before the file is read into
    # memory. Shrink the ceiling so the test needn't write 25 MB.
    monkeypatch.setattr("biosensor.core.MAX_FILE_BYTES", 100)
    big = tmp_path / "big.csv"
    big.write_text("Potential (V),Current (A)\n" + "\n".join(f"{i*0.01},{i*1e-7}" for i in range(50)) + "\n")
    assert big.stat().st_size > 100
    with pytest.raises(FileTooLargeError):
        load(big)
