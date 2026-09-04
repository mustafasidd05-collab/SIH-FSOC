"""sim/render.py -- primitive rasterizer for the virtual scene.

This deliberately does ONLY two things: a near-black background and a bright
beacon blob at each visible target's projected pixel position. No detector
artifacts, no grid overlays, no labels -- realism (turbulence, vibration,
sensor noise) belongs to disturbance/, and HUD overlays belong to ui/. Keeping
this module primitive is what lets disturbance/ inject into a clean image.

The blob is an additive Gaussian (filled circle with soft falloff), which is
the classic PSF-like rendering for an unresolved point source: the optical
beacon is tiny at km range, so the sensor sees its point-spread, not a disc.
Rendered as a warm-white accent (BGR) so it is unambiguous against the
near-black background.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Sequence

import numpy as np

from core.contracts import CameraState, SimFrame, TargetState
from sim.camera import project_target

if TYPE_CHECKING:
    from sim.scene import BeaconConfig

__all__ = ["RenderConfig", "render"]

_BACKGROUND = (8, 9, 12)  # BGR, near-black with a hint of blue
_BEACON_COLOR = (235, 244, 250)  # BGR, warm white


@dataclass(frozen=True)
class RenderConfig:
    """Tuning knobs for render(). Defaults are sane for a 1280x720 frame."""

    background_bgr: tuple[int, int, int] = _BACKGROUND
    beacon_bgr: tuple[int, int, int] = _BEACON_COLOR
    beacon_radius_px: float = 6.0  # Gaussian sigma, not hard disc radius
    peak_intensity: float = 255.0


def render(
    targets: Sequence[TargetState],
    camera: CameraState,
    frame_id: int,
    timestamp_s: float,
    config: RenderConfig = RenderConfig(),
    beacon_configs: Sequence[BeaconConfig] | None = None,
) -> SimFrame:
    """Rasterize targets onto a fresh frame and return it as a SimFrame."""
    h, w = camera.height_px, camera.width_px
    image = np.empty((h, w, 3), dtype=np.float32)
    image[..., 0] = config.background_bgr[0]
    image[..., 1] = config.background_bgr[1]
    image[..., 2] = config.background_bgr[2]

    beacon_map: dict[int, BeaconConfig] = {}
    if beacon_configs is not None:
        beacon_map = {b.target_id: b for b in beacon_configs}

    for target in targets:
        if not target.visible:
            continue
        px, py = project_target(target, camera)
        if px < 0 or px >= w or py < 0 or py >= h:
            continue

        radius_px = config.beacon_radius_px
        peak_intensity = config.peak_intensity

        if target.target_id in beacon_map:
            b_cfg = beacon_map[target.target_id]
            if b_cfg.beacon_radius_px is not None:
                radius_px = b_cfg.beacon_radius_px
            if b_cfg.peak_intensity is not None:
                peak_intensity = b_cfg.peak_intensity

        _draw_beacon(
            image,
            px,
            py,
            radius_px=radius_px,
            peak_intensity=peak_intensity,
            beacon_bgr=config.beacon_bgr,
        )

    sim = np.clip(image, 0.0, 255.0).astype(np.uint8)
    return SimFrame(frame_id=frame_id, timestamp_s=timestamp_s, image=sim, camera=camera)


def _draw_beacon(
    image: np.ndarray,
    px: float,
    py: float,
    radius_px: float,
    peak_intensity: float,
    beacon_bgr: tuple[int, int, int],
) -> None:
    """Additively blend a Gaussian blob centred at (px, py) into the float image.

    Values are float32 with the background pre-filled; the caller clips and
    casts to uint8. Additive blending keeps overlapping beacons distinguishable
    and harmless to the eventual detector.
    """
    h, w = image.shape[:2]
    sigma = max(radius_px / 3.0, 1.0)
    r = int(math.ceil(3.0 * sigma))
    x0, x1 = int(px) - r, int(px) + r + 1
    y0, y1 = int(py) - r, int(py) + r + 1
    if x1 <= 0 or y1 <= 0 or x0 >= w or y0 >= h:
        return

    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist2 = (xx - px) ** 2 + (yy - py) ** 2
    glow = np.exp(-0.5 * dist2 / (sigma * sigma)) * (peak_intensity / 255.0)

    x0_c, x1_c = max(0, x0), min(w, x1)
    y0_c, y1_c = max(0, y0), min(h, y1)
    if x0_c >= x1_c or y0_c >= y1_c:
        return

    gx0, gx1 = x0_c - x0, glow.shape[1] - (x1 - x1_c)
    gy0, gy1 = y0_c - y0, glow.shape[0] - (y1 - y1_c)
    glow_patch = glow[gy0:gy1, gx0:gx1]

    for i, val in enumerate(beacon_bgr):
        image[y0_c:y1_c, x0_c:x1_c, i] += val * glow_patch