"""Unit tests for disturbance/occlusion.py."""

import numpy as np
import pytest

from core.contracts import CameraState, SimFrame
from disturbance.occlusion import OcclusionModel


def _camera() -> CameraState:
    return CameraState(
        pan_rad=0.0, tilt_rad=0.0,
        pan_min_rad=-1.5, pan_max_rad=1.5,
        tilt_min_rad=-0.5, tilt_max_rad=0.5,
        fov_h_rad=0.7,
        fov_v_rad=0.5,
        width_px=640,
        height_px=480,
    )


def test_occlusion_shape_and_contract():
    model = OcclusionModel(num_clouds=2, opacity=0.5, size_px=50.0, seed=42)
    img = np.full((480, 640, 3), 128, dtype=np.uint8)
    f = SimFrame(frame_id=0, timestamp_s=1.5, image=img, camera=_camera())
    out = model(f)
    assert isinstance(out, SimFrame)
    assert out.image.shape == (480, 640, 3)
    assert out.image.dtype == np.uint8


def test_occlusion_zero_opacity_identity():
    model = OcclusionModel(num_clouds=2, opacity=0.0, seed=42)
    img = np.full((480, 640, 3), 128, dtype=np.uint8)
    f = SimFrame(frame_id=0, timestamp_s=1.5, image=img, camera=_camera())
    out = model(f)
    assert np.array_equal(out.image, img)


def test_occlusion_reproducible_with_seed():
    img = np.full((480, 640, 3), 128, dtype=np.uint8)
    m1 = OcclusionModel(num_clouds=2, opacity=0.5, seed=123)
    m2 = OcclusionModel(num_clouds=2, opacity=0.5, seed=123)
    f1 = SimFrame(frame_id=0, timestamp_s=0.5, image=img, camera=_camera())
    f2 = SimFrame(frame_id=0, timestamp_s=0.5, image=img, camera=_camera())
    assert np.array_equal(m1(f1).image, m2(f2).image)
