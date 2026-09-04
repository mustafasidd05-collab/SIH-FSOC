"""Tests for disturbance/sensor_noise.py.

Checks: contract preservation, the measured noise sigma on a flat mid-scale
frame matches the SNR calibration within tolerance, mean brightness is
preserved (zero-mean noise), and shot noise scales with pixel intensity
(bright pixels jitter more than dark ones).
"""

import numpy as np

from core.contracts import SimFrame
from disturbance.sensor_noise import SensorNoiseModel

from fixture_frames import make_flat_frame, make_two_tone_frame


def _assert_contract(out: SimFrame, ref: SimFrame) -> None:
    assert isinstance(out, SimFrame)
    assert out.frame_id == ref.frame_id
    assert out.timestamp_s == ref.timestamp_s
    assert out.camera is ref.camera
    assert out.image.dtype == np.uint8
    assert out.image.shape == ref.image.shape
    assert out.image.min() >= 0 and out.image.max() <= 255


def test_contract_preserved():
    frame = make_flat_frame(value=128, frame_id=3)
    out = SensorNoiseModel(snr_db=22.0, seed=7)(frame)
    _assert_contract(out, frame)


def test_noise_sigma_matches_snr_calibration():
    for snr_db in (35.0, 22.0, 12.0):
        model = SensorNoiseModel(snr_db=snr_db, seed=11)
        frame = make_flat_frame(value=128)
        stds = [model(frame).image.std() for _ in range(8)]
        measured = float(np.mean(stds))
        expected = 255.0 / (10.0 ** (snr_db / 20.0))
        assert np.isclose(measured, expected, rtol=0.15), (
            f"snr={snr_db} dB: measured sigma {measured:.2f} vs expected {expected:.2f}"
        )


def test_mean_preserved():
    model = SensorNoiseModel(snr_db=22.0, seed=13)
    frame = make_flat_frame(value=128)
    means = [model(frame).image.mean() for _ in range(10)]
    assert abs(float(np.mean(means)) - 128.0) < 1.0


def test_shot_noise_scales_with_intensity():
    snr_db, f_frac = 22.0, 0.30
    model = SensorNoiseModel(snr_db=snr_db, read_noise_fraction=f_frac, seed=17)
    # Right half at 180, not 255: at full scale the Gaussian shot tail clips at
    # the 255 saturation (a real detector behaviour) and the measured std is
    # no longer a fair probe of the calibration formula.
    frame = make_two_tone_frame(left_value=10, right_value=180)
    h, w = frame.image.shape[:2]
    stds_left = []
    stds_right = []
    for _ in range(10):
        out = model(frame)
        stds_left.append(out.image[:, : w // 2, :].std())
        stds_right.append(out.image[:, w // 2 :, :].std())
    left, right = float(np.mean(stds_left)), float(np.mean(stds_right))
    assert right > left, f"shot noise must grow with intensity: right {right:.2f} vs left {left:.2f}"

    # Hand-computed drops: the documented calibration says noise on a pixel of
    # intensity I has variance sigma_read^2 + k*I with k calibrated at the
    # reference intensity so that sigma_total = 255/10^(snr_db/20) at I=128.
    sigma_total = 255.0 / (10.0 ** (snr_db / 20.0))
    sigma_read = sigma_total * f_frac
    k = sigma_total**2 * (1.0 - f_frac**2) / 128.0
    left_exp = np.sqrt(sigma_read**2 + k * 10.0)
    right_exp = np.sqrt(sigma_read**2 + k * 180.0)
    assert np.isclose(left, left_exp, rtol=0.15), f"left {left:.2f} vs {left_exp:.2f}"
    assert np.isclose(right, right_exp, rtol=0.15), f"right {right:.2f} vs {right_exp:.2f}"
    assert right > 2.0 * sigma_read


def test_clipping_bounds():
    model = SensorNoiseModel(snr_db=12.0, seed=19)
    frame = make_flat_frame(value=128)
    for _ in range(5):
        out = model(frame)
        assert out.image.min() >= 0 and out.image.max() <= 255


def test_seed_reproducibility():
    a = SensorNoiseModel(snr_db=22.0, seed=3)
    b = SensorNoiseModel(snr_db=22.0, seed=3)
    fa = make_flat_frame(value=128)
    for _ in range(5):
        fa = a(fa)
    fb = make_flat_frame(value=128)
    for _ in range(5):
        fb = b(fb)
    np.testing.assert_array_equal(fa.image, fb.image)