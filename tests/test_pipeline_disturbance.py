"""Tests for disturbance/pipeline.py.

Checks: named profile table is complete and its parameters are inside the
documented mild/moderate/severe ranges, single-frame application preserves
the contract, the pipeline is deterministic under a seed, and a 120-frame
clip degrades monotonically with severity (beacon peak loss and frame-mean
noise both grow mild < moderate < severe).
"""

import numpy as np
import pytest

from core.contracts import SimFrame
from disturbance import PROFILES, DisturbancePipeline, apply_profile
from disturbance.camera_motion_blur import CameraMotionBlurModel
from disturbance.occlusion import OcclusionModel
from disturbance.sensor_noise import SensorNoiseModel
from disturbance.turbulence import TurbulenceModel
from disturbance.vibration import VibrationModel

from fixture_frames import make_camera, make_frame, frame_std, beacon_window_mask


def _assert_contract(out: SimFrame, ref: SimFrame) -> None:
    assert isinstance(out, SimFrame)
    assert out.frame_id == ref.frame_id
    assert out.timestamp_s == ref.timestamp_s
    assert out.camera is ref.camera
    assert out.image.dtype == np.uint8
    assert out.image.shape == ref.image.shape
    assert out.image.min() >= 0 and out.image.max() <= 255


def test_profiles_cover_three_severities():
    assert set(PROFILES) == {"mild", "moderate", "severe"}
    for name, p in PROFILES.items():
        assert p.name == name
        assert p.turbulence and p.vibration and p.sensor_noise


def test_profile_parameters_within_documented_ranges():
    documented = {
        "blur_sigma_px": {"mild": 0.4, "moderate": 1.2, "severe": 2.5},
        "scint_sigma": {"mild": 0.05, "moderate": 0.15, "severe": 0.35},
        "displacement_sigma_px": {"mild": 0.4, "moderate": 1.5, "severe": 3.5},
        "tau_s": {"mild": 0.05, "moderate": 0.2, "severe": 0.8},
        "snr_db": {"mild": 35.0, "moderate": 22.0, "severe": 12.0},
    }
    for param, severities in documented.items():
        for severity, expected in severities.items():
            section = (
                PROFILES[severity].turbulence
                if param.startswith(("blur", "scint"))
                else PROFILES[severity].vibration
                if param.startswith(("displacement", "tau"))
                else PROFILES[severity].sensor_noise
            )
            assert section[param] == expected, (
                f"{severity}.{param}: documented range value {expected} must be the profile value"
            )


def test_apply_profile_single_frame_contract():
    frame = make_frame()
    for name in PROFILES:
        out = apply_profile(frame, name, seed=1)
        _assert_contract(out, frame)


def test_pipeline_matches_manual_sequence():
    # Pipeline output must equal manually chaining turbulence -> occlusion ->
    # camera motion blur -> vibration -> sensor noise with the same per-model seeds.
    seed = 5
    frame = make_frame(frame_id=1, timestamp_s=1 / 30.0)
    out = DisturbancePipeline("mild", seed=seed).apply(frame)
    _assert_contract(out, frame)

    manual = make_frame(frame_id=1, timestamp_s=1 / 30.0)
    turb = TurbulenceModel(seed=seed, **PROFILES["mild"].turbulence)
    occ = OcclusionModel(seed=seed + 1, **PROFILES["mild"].occlusion)
    cmb = CameraMotionBlurModel(seed=seed + 2, **PROFILES["mild"].camera_motion_blur)
    vib = VibrationModel(seed=seed + 3, **PROFILES["mild"].vibration)
    sens = SensorNoiseModel(seed=seed + 4, **PROFILES["mild"].sensor_noise)
    manual = sens(vib(cmb(occ(turb(manual)))))
    np.testing.assert_array_equal(out.image, manual.image)


def test_unknown_profile_rejected():
    with pytest.raises(KeyError):
        DisturbancePipeline("bogus")

    with pytest.raises(KeyError):
        apply_profile(make_frame(), "bogus")


def test_apply_profile_determinism():
    frame = make_frame()
    a = apply_profile(frame, "moderate", seed=99)
    b = apply_profile(frame, "moderate", seed=99)
    np.testing.assert_array_equal(a.image, b.image)


@pytest.mark.parametrize("name", ["mild", "moderate", "severe"])
def test_clip_contract_every_frame(name):
    pipe = DisturbancePipeline(name, seed=10)
    cam = make_camera()
    out = None
    for i in range(120):
        out = pipe.apply(make_frame(frame_id=i, timestamp_s=i / 30.0, camera=cam))
        _assert_contract(out, make_frame(frame_id=i, timestamp_s=i / 30.0, camera=cam))
    assert out is not None


def test_clip_degradation_monotonic_with_severity():
    fps = 30.0
    contrast_means = {}
    noise_means = {}
    clean = make_frame()
    mask = beacon_window_mask(clean)
    for name in PROFILES:
        pipe = DisturbancePipeline(name, seed=10)
        contrasts, stds = [], []
        for i in range(120):
            frame = pipe.apply(make_frame(frame_id=i, timestamp_s=i / fps))
            win_mean = float(frame.image[mask].mean())
            bg_mean = float(frame.image[:60, :60].mean())
            stds.append(frame_std(frame))
            contrasts.append((win_mean - bg_mean) / max(stds[-1], 1e-6))
        contrast_means[name] = float(np.mean(contrasts))
        noise_means[name] = float(np.mean(stds))

    # Signal-to-background contrast (win_mean - bg) / frame_std must shrink
    # with severity -- brightness loss in the numerator, noise rise in the
    # denominator -- and frame-mean noise must grow.
    assert (
        contrast_means["mild"] > contrast_means["moderate"] > contrast_means["severe"]
    ), contrast_means
    assert noise_means["mild"] < noise_means["moderate"] < noise_means["severe"]
    assert contrast_means["severe"] < 0.5 * contrast_means["mild"]