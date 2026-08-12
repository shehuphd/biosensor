from pathlib import Path

import pandas as pd

from biosensor.core import batch_load, load, to_dataframe

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
