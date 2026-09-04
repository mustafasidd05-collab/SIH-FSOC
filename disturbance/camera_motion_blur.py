"""disturbance/camera_motion_blur.py -- directional motion blur from camera angular velocity.

When the pan-tilt camera rotates (gimbal movement), the sensor integrates light
over the exposure time. Rapid rotation smears point sources (beacons) into streaks
aligned with the instantaneous direction of motion (pan and tilt rates).

This model computes pan/tilt angular velocity between successive frames:
    omega_pan = (pan_curr - pan_prev) / dt
    omega_tilt = (tilt_curr - tilt_prev) / dt
and derives a directional motion blur kernel whose length is proportional to
sqrt(omega_pan^2 + omega_tilt^2) and whose angle is atan2(-omega_tilt, omega_pan).

Range guide (blur_gain, max_kernel_size):
    blur_gain        mild 5.0    moderate 15.0  severe 30.0
    max_kernel_size  mild 5      moderate 9     severe 19
"""

from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np

from core.contracts import CameraState, SimFrame


class CameraMotionBlurModel:
    """Stateful camera motion blur injector based on gimbal angular velocity.

    Parameters
    ----------
    blur_gain : float
        Scaling factor converting angular speed (rad/s) to pixel blur kernel length.
    max_kernel_size : int
        Maximum kernel dimension (must be odd).
    dt_fallback_s : float
        Seconds assumed per frame when timestamps are flat (e.g. frame 0).
    seed : int | None
        Unused by deterministic velocity blur, accepted for pipeline consistency.
    """

    def __init__(
        self,
        blur_gain: float = 15.0,
        max_kernel_size: int = 9,
        dt_fallback_s: float = 1.0 / 60.0,
        seed: int | None = None,
    ) -> None:
        if blur_gain < 0:
            raise ValueError("blur_gain must be >= 0")
        if max_kernel_size < 1 or max_kernel_size % 2 == 0:
            raise ValueError("max_kernel_size must be an odd integer >= 1")
        if dt_fallback_s <= 0:
            raise ValueError("dt_fallback_s must be > 0")

        self.blur_gain = blur_gain
        self.max_kernel_size = max_kernel_size
        self.dt_fallback_s = dt_fallback_s
        self._prev_camera: CameraState | None = None
        self._prev_timestamp_s: float | None = None

    def reset(self, seed: int | None = None) -> None:
        """Reset internal history (previous camera state and timestamp)."""
        self._prev_camera = None
        self._prev_timestamp_s = None

    def __call__(self, frame: SimFrame) -> SimFrame:
        if self._prev_timestamp_s is None or frame.timestamp_s <= self._prev_timestamp_s or self._prev_camera is None:
            dt = self.dt_fallback_s
            d_pan = 0.0
            d_tilt = 0.0
        else:
            dt = frame.timestamp_s - self._prev_timestamp_s
            d_pan = frame.camera.pan_rad - self._prev_camera.pan_rad
            d_tilt = frame.camera.tilt_rad - self._prev_camera.tilt_rad

        self._prev_timestamp_s = frame.timestamp_s
        self._prev_camera = frame.camera

        if dt <= 0:
            dt = self.dt_fallback_s

        omega_pan = d_pan / dt
        omega_tilt = d_tilt / dt  # positive tilt up -> negative pixel y change

        speed = float(np.hypot(omega_pan, omega_tilt))
        if speed < 1e-4 or self.blur_gain <= 0:
            return frame

        blur_len = self.blur_gain * speed
        k = int(min(self.max_kernel_size, 2 * int(blur_len / 2) + 1))
        if k < 3:
            return frame

        # Direction angle in image plane (x right, y down)
        # Pan right (+ omega_pan) moves image left (-x)
        # Tilt up (+ omega_tilt) moves image down (+y)
        angle_rad = float(np.arctan2(-omega_tilt, -omega_pan))

        kernel = _make_directional_kernel(k, angle_rad)
        h, w = frame.image.shape[:2]
        img_float = frame.image.astype(np.float32)
        blurred = cv2.filter2D(img_float, -1, kernel, borderType=cv2.BORDER_REPLICATE)
        out = np.clip(blurred, 0, 255).astype(np.uint8)
        return replace(frame, image=out)


def _make_directional_kernel(k: int, angle_rad: float) -> np.ndarray:
    """Create a normalized 2D directional motion blur kernel of size k x k."""
    kernel = np.zeros((k, k), dtype=np.float32)
    center = k // 2
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)

    # Sub-pixel line sampling along the blur axis
    steps = max(k * 2, 5)
    for s in range(steps):
        t = (s / (steps - 1) - 0.5) * (k - 1)
        fx = center + t * cos_a
        fy = center + t * sin_a

        x0, y0 = int(np.floor(fx)), int(np.floor(fy))
        x1, y1 = x0 + 1, y0 + 1
        tx, ty = fx - x0, fy - y0

        if 0 <= x0 < k and 0 <= y0 < k:
            kernel[y0, x0] += (1.0 - tx) * (1.0 - ty)
        if 0 <= x1 < k and 0 <= y0 < k:
            kernel[y0, x1] += tx * (1.0 - ty)
        if 0 <= x0 < k and 0 <= y1 < k:
            kernel[y1, x0] += (1.0 - tx) * ty
        if 0 <= x1 < k and 0 <= y1 < k:
            kernel[y1, x1] += tx * ty

    total = kernel.sum()
    if total > 0:
        kernel /= total
    else:
        kernel[center, center] = 1.0
    return kernel
