"""Unit tests for disturbance/camera_motion_blur.py."""

import numpy as np
import pytest

from core.contracts import CameraState, SimFrame
from disturbance.camera_motion_blur import CameraMotionBlurModel


def _camera(pan: float = 0.0, tilt: float = 0.0) -> CameraState:
    return CameraState(
        pan_rad=pan,
        tilt_rad=tilt,
        pan_min_rad=-1.5,
        pan_max_rad=1.5,
        tilt_min_rad=-0.5,
        tilt_max_rad=0.5,
        fov_h_rad=0.7,
        fov_v_rad=0.5,
        width_px=640,
        height_px=480,
    )


def test_camera_motion_blur_zero_motion_identity():
    model = CameraMotionBlurModel()
    img = np.full((480, 640, 3), 100, dtype=np.uint8)
    cam = _camera(pan=0.0, tilt=0.0)
    f1 = SimFrame(frame_id=0, timestamp_s=0.0, image=img, camera=cam)
    f2 = SimFrame(frame_id=1, timestamp_s=1.0 / 60.0, image=img, camera=cam)

    model(f1)
    out = model(f2)
    assert np.array_equal(out.image, img)


def test_camera_motion_blur_pans_stretches():
    model = CameraMotionBlurModel(blur_gain=20.0, max_kernel_size=9)
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[240, 320] = [255, 255, 255]

    cam1 = _camera(pan=0.0, tilt=0.0)
    cam2 = _camera(pan=0.1, tilt=0.0)

    f1 = SimFrame(frame_id=0, timestamp_s=0.0, image=img, camera=cam1)
    f2 = SimFrame(frame_id=1, timestamp_s=1.0 / 60.0, image=img, camera=cam2)

    model(f1)
    out = model(f2)
    assert out.image.shape == (480, 640, 3)
    assert out.image.dtype == np.uint8
    assert float(out.image[240, 320].max()) < 255.0
    assert float(out.image[240, 321].max()) > 0.0 or float(out.image[240, 319].max()) > 0.0
