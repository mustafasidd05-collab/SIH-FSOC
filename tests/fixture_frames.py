"""tests/fixture_frames.py -- throwaway SimFrame generator for disturbance/ tests.

The disturbance module is only allowed to depend on core/contracts.py, so its
tests build their own synthetic scene: a bright filled circle (the beacon) on
a dark background, exactly like the sim/ module will produce at integration
time. Duplicating this tiny generator here is intentional -- it keeps
disturbance/ testable in complete isolation from sim/.
"""

import cv2
import numpy as np

from core.contracts import CameraState, SimFrame

BEACON_RADIUS = 10
BACKGROUND = 10
PEAK = 255


def make_camera(width_px: int = 640, height_px: int = 480) -> CameraState:
    return CameraState(
        pan_rad=0.0,
        tilt_rad=0.0,
        pan_min_rad=-1.5,
        pan_max_rad=1.5,
        tilt_min_rad=-0.5,
        tilt_max_rad=0.5,
        fov_h_rad=0.7,
        fov_v_rad=0.5,
        width_px=width_px,
        height_px=height_px,
    )


def make_frame(
    frame_id: int = 0,
    timestamp_s: float = 0.0,
    width_px: int = 640,
    height_px: int = 480,
    center: tuple[int, int] | None = None,
    radius: int = BEACON_RADIUS,
    background: int = BACKGROUND,
    peak: int = PEAK,
    camera: CameraState | None = None,
) -> SimFrame:
    """uint8 BGR frame, dark background, one bright filled circle (beacon)."""
    if center is None:
        center = (width_px // 2, height_px // 2)
    img = np.full((height_px, width_px, 3), background, dtype=np.uint8)
    cv2.circle(img, center, radius, (peak, peak, peak), thickness=-1)
    return SimFrame(
        frame_id=frame_id,
        timestamp_s=timestamp_s,
        image=img,
        camera=camera or make_camera(width_px, height_px),
    )


def make_flat_frame(
    value: int = 128,
    frame_id: int = 0,
    timestamp_s: float = 0.0,
    width_px: int = 640,
    height_px: int = 480,
    camera: CameraState | None = None,
) -> SimFrame:
    """Uniform frame at ``value`` -- used to calibrate noise statistics."""
    img = np.full((height_px, width_px, 3), value, dtype=np.uint8)
    return SimFrame(
        frame_id=frame_id,
        timestamp_s=timestamp_s,
        image=img,
        camera=camera or make_camera(width_px, height_px),
    )


def make_two_tone_frame(
    left_value: int = 10,
    right_value: int = 255,
    frame_id: int = 0,
    timestamp_s: float = 0.0,
    width_px: int = 640,
    height_px: int = 480,
    camera: CameraState | None = None,
) -> SimFrame:
    """Half-dark / half-bright frame -- shot noise must scale with intensity."""
    img = np.full((height_px, width_px, 3), left_value, dtype=np.uint8)
    img[:, width_px // 2 :, :] = right_value
    return SimFrame(
        frame_id=frame_id,
        timestamp_s=timestamp_s,
        image=img,
        camera=camera or make_camera(width_px, height_px),
    )


def beacon_window_mask(
    frame: SimFrame,
    center: tuple[int, int] | None = None,
    radius: int = BEACON_RADIUS,
    margin: int = 8,
) -> np.ndarray:
    """Boolean mask of a search window around the nominal beacon position.

    Used to measure beacon brightness without knowing exactly where the
    beacon ended up after a disturbance (vibration can move it by several px).
    """
    h, w = frame.image.shape[:2]
    if center is None:
        center = (w // 2, h // 2)
    cx, cy = center
    r = radius + margin
    mask = np.zeros((h, w), dtype=bool)
    mask[max(0, cy - r) : cy + r + 1, max(0, cx - r) : cx + r + 1] = True
    return mask


def beacon_brightness(frame: SimFrame, **kw) -> float:
    """Peak pixel value inside the search window around the nominal beacon."""
    mask = beacon_window_mask(frame, **kw)
    return float(frame.image[mask].max())


def frame_mean(frame: SimFrame) -> float:
    return float(frame.image.mean())


def frame_std(frame: SimFrame) -> float:
    return float(frame.image.std())