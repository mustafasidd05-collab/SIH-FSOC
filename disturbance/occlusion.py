"""disturbance/occlusion.py -- soft-edged translucent cloud obstructions.

Simulates physical line-of-sight obstructions (e.g. atmospheric clouds, dust clouds,
debris passing through the optical field of view). Unlike random noise or dropouts,
structured occlusion creates moving translucent patches that partially attenuate
beacon intensity and create spatial-temporal attenuation patterns across the frame.

Parameters (num_clouds, speed_px_s, opacity, size_px):
    num_clouds  mild 1      moderate 2      severe 3
    speed_px_s  mild 20.0   moderate 50.0   severe 90.0
    opacity     mild 0.2    moderate 0.5    severe 0.8
    size_px     mild 40.0   moderate 80.0   severe 150.0
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from core.contracts import SimFrame


class OcclusionModel:
    """Stateful moving translucent cloud occlusion injector.

    Parameters
    ----------
    num_clouds : int
        Number of independent cloud patches drifting across the frame.
    speed_px_s : float
        Drift speed magnitude in pixels per second.
    opacity : float
        Maximum opacity of the clouds (0.0 = invisible, 1.0 = opaque).
    size_px : float
        Characteristic radius (sigma) of the cloud Gaussian spread in pixels.
    seed : int | None
        Seed for cloud initial positions, directions, and appearance.
    """

    def __init__(
        self,
        num_clouds: int = 2,
        speed_px_s: float = 50.0,
        opacity: float = 0.5,
        size_px: float = 80.0,
        seed: int | None = None,
    ) -> None:
        if num_clouds < 0:
            raise ValueError("num_clouds must be >= 0")
        if speed_px_s < 0:
            raise ValueError("speed_px_s must be >= 0")
        if not 0.0 <= opacity <= 1.0:
            raise ValueError("opacity must be between 0.0 and 1.0")
        if size_px <= 0:
            raise ValueError("size_px must be > 0")

        self.num_clouds = num_clouds
        self.speed_px_s = speed_px_s
        self.opacity = opacity
        self.size_px = size_px
        self._rng = np.random.default_rng(seed)
        self._clouds: list[dict[str, np.ndarray]] = []
        self._initialized = False

    def reset(self, seed: int | None = None) -> None:
        """Re-seed RNG and re-initialize cloud paths."""
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._initialized = False
        self._clouds = []

    def _init_clouds(self, width: int, height: int) -> None:
        self._clouds = []
        for _ in range(self.num_clouds):
            pos = np.array(
                [
                    self._rng.uniform(-0.2 * width, 1.2 * width),
                    self._rng.uniform(-0.2 * height, 1.2 * height),
                ],
                dtype=np.float64,
            )
            angle = self._rng.uniform(0.0, 2.0 * np.pi)
            vel = np.array(
                [self.speed_px_s * np.cos(angle), self.speed_px_s * np.sin(angle)],
                dtype=np.float64,
            )
            self._clouds.append({"pos": pos, "vel": vel})
        self._initialized = True

    def __call__(self, frame: SimFrame) -> SimFrame:
        if self.num_clouds == 0 or self.opacity <= 0.0:
            return frame

        h, w = frame.image.shape[:2]
        if not self._initialized:
            self._init_clouds(w, h)

        t = frame.timestamp_s
        img_float = frame.image.astype(np.float32)

        # Coordinate grid for spatial mask evaluation
        xx, yy = np.meshgrid(
            np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32)
        )

        total_mask = np.zeros((h, w), dtype=np.float32)

        for cloud in self._clouds:
            # Position wraps or moves smoothly
            # Center at pos + vel * t (with periodic wrapping across extended bounding box)
            cx = (cloud["pos"][0] + cloud["vel"][0] * t) % (1.4 * w) - 0.2 * w
            cy = (cloud["pos"][1] + cloud["vel"][1] * t) % (1.4 * h) - 0.2 * h

            dist2 = (xx - cx) ** 2 + (yy - cy) ** 2
            # Gaussian cloud shape
            cloud_mask = np.exp(-0.5 * dist2 / (self.size_px * self.size_px))
            total_mask = np.maximum(total_mask, cloud_mask)

        alpha = self.opacity * total_mask
        alpha_3d = alpha[..., np.newaxis]

        # Cloud tint (slightly lighter than background near-black (8, 9, 12), e.g. (18, 20, 28))
        cloud_bgr = np.array([18.0, 20.0, 28.0], dtype=np.float32)

        blended = img_float * (1.0 - alpha_3d) + cloud_bgr * alpha_3d
        out = np.clip(blended, 0, 255).astype(np.uint8)
        return replace(frame, image=out)
