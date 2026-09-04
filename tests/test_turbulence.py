"""Tests for disturbance/turbulence.py.

Checks: contract preservation, blur physics (beacon peak drops with blur
sigma), flat-field conservation (blur of a flat frame is flat; the gain is
mean-1), and temporal correlation of the scintillation walk (AR-1 memory,
not white noise).
"""

import numpy as np

from core.contracts import SimFrame
from disturbance.turbulence import TurbulenceModel

from fixture_frames import make_flat_frame, make_frame, beacon_window_mask, frame_mean


def _assert_contract(out: SimFrame, ref: SimFrame) -> None:
    assert isinstance(out, SimFrame)
    assert out.frame_id == ref.frame_id
    assert out.timestamp_s == ref.timestamp_s
    assert out.camera is ref.camera
    assert out.image.dtype == np.uint8
    assert out.image.shape == ref.image.shape
    assert out.image.shape[2] == 3
    assert out.image.min() >= 0 and out.image.max() <= 255


def test_contract_preserved():
    frame = make_frame()
    out = TurbulenceModel(seed=42)(frame)
    _assert_contract(out, frame)


def test_blur_reduces_beacon_contrast_monotonically():
    frame = make_frame()
    mask = beacon_window_mask(frame)
    # The windowed *peak* is insensitive until sigma approaches the beacon
    # radius (a 10 px disk holds ~all Gaussian mass below sigma~2.5), so the
    # physically meaningful metric is window contrast (std of the windowed
    # region), which drops monotonically as PSF widening erodes the edges.
    contrasts = []
    for sigma in (0.0, 0.4, 1.2, 2.5, 5.0):
        model = TurbulenceModel(
            blur_sigma_px=sigma, blur_jitter_range=(1.0, 1.0), scint_sigma=0.0, seed=1
        )
        model.reset()
        contrasts.append(float(model(frame).image[mask].std()))
    assert all(p > q for p, q in zip(contrasts, contrasts[1:])), contrasts
    # Severe smear must cut the beacon-region contrast by more than a third.
    assert contrasts[-1] < 0.65 * contrasts[0]


def test_scintillation_zero_on_zero_sigma():
    model = TurbulenceModel(
        blur_sigma_px=0.0, blur_jitter_range=(1.0, 1.0), scint_sigma=0.0, seed=1
    )
    out = model(make_frame())
    np.testing.assert_array_equal(out.image, make_frame().image, strict=False)


def test_flat_frame_mean_preserved():
    model = TurbulenceModel(
        blur_sigma_px=1.2, scint_sigma=0.15, scint_rho=0.9, seed=42
    )
    frame = make_flat_frame(value=128, width_px=160, height_px=120)
    means = [frame_mean(model(frame)) for _ in range(3000)]
    means = np.asarray(means)
    # Gain is log-normal mean-1; blur of a flat frame is flat -> mean ~128.
    # The AR(1) reduces the effective sample size (~1/10 of the 3000 draws),
    # so allow a small dispersion around the ideal mean.
    assert abs(float(means.mean()) - 128.0) < 2.5


def test_scintillation_has_memory():
    model = TurbulenceModel(
        blur_sigma_px=0.0, blur_jitter_range=(1.0, 1.0), scint_sigma=0.35, scint_rho=0.9, seed=7
    )
    frame = make_flat_frame(value=128)
    gains = np.asarray([frame_mean(model(frame)) / 128.0 for _ in range(300)])
    x = np.log(gains)
    lag1 = np.corrcoef(x[:-1], x[1:])[0, 1]
    assert lag1 > 0.7, f"scintillation should be temporally correlated, got lag-1 rho={lag1:.3f}"
    assert float(x.std()) < 0.5  # sanity: bounded log-amplitude band


def test_seed_reproducibility():
    a = TurbulenceModel(blur_sigma_px=1.2, scint_sigma=0.15, seed=3)
    b = TurbulenceModel(blur_sigma_px=1.2, scint_sigma=0.15, seed=3)
    fa = make_frame(frame_id=0)
    for i in range(10):
        fa = a(fa)
    fb = make_frame(frame_id=0)
    for i in range(10):
        fb = b(fb)
    np.testing.assert_array_equal(fa.image, fb.image)