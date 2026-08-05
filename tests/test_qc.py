from biosensor_io.qc import sanity_check
from biosensor_io.schema import Measurement


def _measurement(**overrides):
    defaults = dict(
        potential_v=[-0.5, -0.25, 0.0, 0.25, 0.5, 0.25, 0.0, -0.25, -0.5],
        current_a=[1e-7, 2e-7, 5e-7, 3e-6, 1e-7, 3e-6, 5e-7, 2e-7, 1e-7],
        source_filename="test.csv",
    )
    defaults.update(overrides)
    return Measurement(**defaults)


def test_healthy_cv_curve_is_ok():
    qc = sanity_check(_measurement())
    assert qc.sanity_status == "ok"


def test_flat_current_fails():
    qc = sanity_check(_measurement(current_a=[1e-7] * 9))
    assert qc.sanity_status == "failed"
    assert "flat" in qc.sanity_reason


def test_constant_potential_fails():
    qc = sanity_check(_measurement(potential_v=[0.1] * 9))
    assert qc.sanity_status == "failed"


def test_too_few_points_fails():
    qc = sanity_check(_measurement(potential_v=[0.1, 0.2], current_a=[1e-7, 2e-7]))
    assert qc.sanity_status == "failed"


def test_monotonic_sweep_with_no_peak_is_flagged():
    qc = sanity_check(
        _measurement(
            potential_v=[-0.5, -0.25, 0.0, 0.25, 0.5],
            current_a=[1e-7, 2e-7, 3e-7, 4e-7, 5e-7],
        )
    )
    assert qc.sanity_status == "flagged"
