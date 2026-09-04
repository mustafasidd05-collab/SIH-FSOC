"""Tests for disturbance/vibration.py.

Checks: contract preservation, first frame is a no-op (OU starts at zero),
the displacement is a *correlated* walk with memory (not white noise), is
bounded around zero, and the beacon image actually moves by the commanded
displacement.
"""

import numpy as np

from core.contracts import SimFrame
from disturbance.vibration import VibrationModel

from fixture_frames import make_frame


def _assert_contract(out: SimFrame, ref: SimFrame) -> None:
    assert isinstance(out, SimFrame)
    assert out.frame_id == ref.frame_id
    assert out.timestamp_s == ref.timestamp_s
    assert out.camera is ref.camera
    assert out.image.dtype == np.uint8
    assert out.image.shape == ref.image.shape
    assert out.image.min() >= 0 and out.image.max() <= 255


def _displacement_series(model, n_frames: int, fps: float = 60.0) -> np.ndarray:
    model.reset()
    shifts = []
    for i in range(n_frames):
        frame = make_frame(frame_id=i, timestamp_s=i / fps)
        model(frame)
        shifts.append(model.offset_px)
    return np.asarray(shifts)


def test_contract_preserved():
    frame = make_frame(frame_id=5, timestamp_s=0.1)
    out = VibrationModel(seed=42)(frame)
    _assert_contract(out, frame)


def test_state_starts_at_stationary_not_at_zero():
    model = VibrationModel(displacement_sigma_px=3.5, seed=1)
    assert model.offset_px == (0.0, 0.0)  # state is exactly zero pre-call
    sigma = 3.5
    # One sample per fresh model: with 300 independent stationary draws the
    # std of the first-frame displacement must sit near sigma (a ramp-up from
    # zero would measure far below it). Measured over runs, not within one
    # heavily-correlated series.
    firsts = []
    for i in range(300):
        m = VibrationModel(displacement_sigma_px=sigma, tau_s=0.8, seed=1000 + i)
        m(make_frame(frame_id=0, timestamp_s=0.0))
        firsts.append(m.offset_px)
    firsts = np.asarray(firsts)
    assert float(firsts.std(axis=0).mean()) > 0.85 * sigma
    assert float(np.abs(firsts).mean()) > 0.5 * sigma  # E|N(0,sigma)| = 0.798*sigma


def test_displacement_is_bounded_and_correctly_scaled():
    sigma = 3.5
    shifts = _displacement_series(VibrationModel(displacement_sigma_px=sigma, tau_s=0.8, seed=2), 600)
    std = shifts.std(axis=0)
    assert std.mean() < 1.4 * sigma and std.mean() > 0.7 * sigma
    assert np.abs(shifts).max() < 4.5 * sigma


def test_displacement_has_memory_not_white_noise():
    tau = 0.8
    shifts = _displacement_series(VibrationModel(displacement_sigma_px=2.0, tau_s=tau, seed=3), 600, fps=60)
    # dt=1/60 s, rho = exp(-dt/tau) ~ 0.979 -> lag-1 autocorr should be high.
    d = shifts[:, 0]
    lag1 = np.corrcoef(d[:-1], d[1:])[0, 1]
    assert lag1 > 0.8, f"vibration must be a correlated walk, got lag-1 rho={lag1:.3f}"


def test_beacon_moves_with_displacement():
    model = VibrationModel(displacement_sigma_px=3.5, tau_s=0.8, seed=5)
    shifts = []
    frame = make_frame(center=(320, 240))
    for i in range(120):
        frame = model(make_frame(frame_id=i, timestamp_s=i / 60.0, center=(320, 240)))
        shifts.append(model.offset_px)
    dx, dy = shifts[-1]
    # Centroid of the bright plateau (thresholded window, like a tracker would
    # compute) -- for a filled disk the centroid equals the shifted center.
    ys, xs = np.nonzero(frame.image[..., 0] > 200)
    moved = (float(xs.mean()) - 320.0, float(ys.mean()) - 240.0)
    assert np.abs(moved[0] - dx) <= 1.0 and np.abs(moved[1] - dy) <= 1.0, (
        f"beacon centroid moved {moved} but commanded shift was ({dx:.2f}, {dy:.2f})"
    )


def test_zero_disturbance_is_identity():
    model = VibrationModel(displacement_sigma_px=0.0, seed=1)
    frame = make_frame()
    out = model(frame)
    np.testing.assert_array_equal(out.image, frame.image)