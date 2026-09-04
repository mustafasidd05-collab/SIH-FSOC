"""Unit tests for tracking/kalman.py -- constant-velocity Kalman filter.

Verification style: known trajectories, sanity bounds on error, and the
lifecycle (inactive until initialized, predict-only during dropouts).
"""

import numpy as np
import pytest

from tracking.kalman import KalmanTracker


def _linear_truth(n: int, x0: float = 100.0, vx: float = 2.0, y0: float = 200.0, vy: float = 1.0):
    t = np.arange(n) / 60.0
    return np.stack([x0 + vx * t, y0 + vy * t], axis=1)


def test_lifecycle():
    kf = KalmanTracker()
    assert not kf.active
    assert kf.predict(1 / 60) is None
    with pytest.raises(RuntimeError):
        kf.update((1.0, 1.0))

    kf.initialize((10.0, 20.0))
    assert kf.active
    assert kf.mean_px == (10.0, 20.0)

    kf.reset()
    assert not kf.active
    assert kf.mean_px is None


def test_update_moves_posterior_toward_measurement():
    kf = KalmanTracker()
    kf.initialize((0.0, 0.0))
    kf.predict(1 / 60)
    mean = kf.update((50.0, -20.0))
    assert mean[0] > 0.0 and mean[0] < 50.0  # pulled toward, not to, the measurement
    assert mean[1] < 0.0 and mean[1] > -20.0


def test_smoothing_reduces_noise_vs_raw_measurements():
    truth = _linear_truth(120)
    rng = np.random.default_rng(11)
    measurements = truth + rng.normal(0.0, 3.0, truth.shape)

    kf = KalmanTracker()
    kf.initialize(tuple(measurements[0]))
    filtered = [kf.mean_px]
    for i in range(1, len(truth)):
        kf.predict(1 / 60)
        filtered.append(kf.update(tuple(measurements[i])))

    filtered = np.asarray(filtered)
    raw_rmse = float(np.sqrt(np.mean((measurements - truth) ** 2)))
    filt_rmse = float(np.sqrt(np.mean((filtered - truth) ** 2)))
    assert filt_rmse < raw_rmse * 0.8
    assert filt_rmse < 1.5  # sigma=3px noise smoothed to well under 1.5px


def test_predict_only_during_dropout_tracks_truth():
    # Train on 80 frames, then predict-only for 20 frames (dropout). The
    # constant-velocity extrapolation must stay near the true continuation.
    truth = _linear_truth(100)
    rng = np.random.default_rng(23)
    measurements = truth + rng.normal(0.0, 3.0, truth.shape)

    kf = KalmanTracker()
    kf.initialize(tuple(measurements[0]))
    for i in range(1, 80):
        kf.predict(1 / 60)
        kf.update(tuple(measurements[i]))

    errors = []
    for i in range(80, 100):
        predicted = kf.predict(1 / 60)
        assert predicted is not None
        errors.append(float(np.hypot(predicted[0] - truth[i, 0], predicted[1] - truth[i, 1])))

    assert max(errors) < 10.0  # 20-frame, 0.33 s extrapolation stays within 10 px
    assert np.mean(errors) < max(errors)  # sanity: mean well defined


def test_inactive_filter_has_no_covariance():
    kf = KalmanTracker()
    assert kf.covariance is None
    kf.initialize((1.0, 2.0))
    assert kf.covariance is not None
    assert kf.covariance.shape == (4, 4)