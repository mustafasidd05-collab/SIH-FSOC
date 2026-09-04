"""tests/fixtures/generate_clips.py -- deterministic synthetic beacon clips.

Generates three clips (seeded RNG, so reproducible across machines):

    clip_clean.npz   -- 300 frames @ 60 fps, bright Gaussian dot (~255 peak)
                        on a black background, smooth path. No sensor noise.
    clip_noisy.npz   -- same path + Gaussian sensor noise (sigma=10) on
                        every frame (stands in for disturbance/ output until
                        that module lands).
    clip_dropout.npz -- noisy clip with a scripted 15-frame TOTAL dropout
                        (beacon fully removed, frames 120..134 inclusive),
                        then the beacon reappears on its path. Exercises the
                        LOST -> REACQUIRE path of the state machine.

Ground truth per frame: analytic float path position and visibility. The
path (parametric, see _beacon_path) is deliberately gentle during the
dropout window so the Kalman velocity extrapolation is nearly exact -- the
gate check then measures the state machine, not the motion model.

Run directly:  python -m tests.fixtures.generate_clips
or import generate_clips(out_dir).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
NUM_FRAMES = 300
FPS = 60.0
FRAME_PERIOD_S = 1.0 / FPS

# Noisy clips are recorded at quarter area (640x360): raw Gaussian sensor
# noise is entropy that zip/deflate cannot compress, and 300 frames of it at
# 1280x720 would be ~380 MB per clip. Stats, motion in px, and detector
# behavior are unchanged -- this is only a file-footprint decision.
NOISY_WIDTH = 640
NOISY_HEIGHT = 360

# Beacon appearance.
BEACON_RADIUS_PX = 3
BEACON_PEAK = 255
BLUR_KERNEL = (5, 5)
BLUR_SIGMA = 1.5

# Sensor noise (injected on top of the beacon, like disturbance/ will).
NOISE_SIGMA = 10.0

# Scripted dropout window (inclusive frame indices; beacon entirely absent).
DROPOUT_START = 120
DROPOUT_END = 134  # inclusive -> 15 frames

CLIPS = ("clip_clean", "clip_noisy", "clip_dropout")


def _beacon_path_px(frame: int, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT) -> tuple[float, float]:
    """Parametric beacon path scaled to the clip's frame dimensions.

    x: linear ramp across the middle 70% of the width; y: slow sine ripple
    covering the middle 80% of the height.  Motion stays gentle (dx ~ 2.7
    px/frame @ 1280x720, proportionally scaled for smaller frames) and is
    nearly constant-velocity over the dropout window -- exactly what we need
    to test the state machine without confounding kinematics.
    """
    f = frame / (NUM_FRAMES - 1)
    x_margin = 0.15 * width
    y_half = height / 2.0
    y_margin = 0.40 * y_half
    x = x_margin + (width - 2.0 * x_margin) * f
    y = y_half + y_margin * np.sin(0.3 + 2.2 * f)
    return (float(x), float(y))


def _render_frame(
    center_px: tuple[float, float] | None,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    if center_px is not None:
        cx, cy = center_px
        cv2.circle(img, (round(cx), round(cy)), BEACON_RADIUS_PX, (BEACON_PEAK,) * 3, -1)
    img = cv2.GaussianBlur(img, BLUR_KERNEL, BLUR_SIGMA)
    return img


def _build_clip(noisy: bool, dropout: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(20260830)
    width = NOISY_WIDTH if noisy else FRAME_WIDTH
    height = NOISY_HEIGHT if noisy else FRAME_HEIGHT
    images = np.empty((NUM_FRAMES, height, width, 3), dtype=np.uint8)
    gt_xy = np.full((NUM_FRAMES, 2), -1.0)  # (-1, -1) marks hidden beacon
    gt_visible = np.zeros(NUM_FRAMES, dtype=bool)

    for frame in range(NUM_FRAMES):
        hidden = dropout and DROPOUT_START <= frame <= DROPOUT_END
        center = None if hidden else _beacon_path_px(frame, width=width, height=height)

        img = _render_frame(center, width=width, height=height)
        if noisy:
            noise = rng.normal(0.0, NOISE_SIGMA, img.shape)
            img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)

        images[frame] = img
        if not hidden:
            gt_xy[frame, 0], gt_xy[frame, 1] = center  # type: ignore[assignment]
            gt_visible[frame] = True

    return images, gt_xy, gt_visible


def generate_clips(out_dir: str | Path = "tests/fixtures/clips") -> dict[str, Path]:
    """Generate (or regenerate) all three clips; returns path per clip."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    specs = {
        "clip_clean": dict(noisy=False, dropout=False),
        "clip_noisy": dict(noisy=True, dropout=False),
        "clip_dropout": dict(noisy=True, dropout=True),
    }

    paths: dict[str, Path] = {}
    for name, spec in specs.items():
        images, gt_xy, gt_visible = _build_clip(**spec)  # type: ignore[arg-type]
        path = out_dir / f"{name}.npz"
        # Compressed: clean frames are mostly black, and even noisy frames
        # compress well. Raw savez would emit ~830 MB per clip.
        np.savez_compressed(
            path,
            images=images,
            gt_xy=gt_xy,
            gt_visible=gt_visible,
            width=images.shape[2],
            height=images.shape[1],
            fps=float(FPS),
            noise_sigma=float(NOISE_SIGMA) if spec["noisy"] else 0.0,
            dropout_start=int(DROPOUT_START) if spec["dropout"] else -1,
            dropout_end=int(DROPOUT_END) if spec["dropout"] else -1,
        )
        paths[name] = path
    return paths


def load_clip(name: str) -> dict:
    """Load one clip back as plain dicts (used by tests + self-verify)."""
    assert name in CLIPS, f"unknown clip {name!r}"
    path = Path("tests/fixtures/clips") / f"{name}.npz"
    with np.load(path) as data:
        return {key: data[key] for key in data.files}


if __name__ == "__main__":
    for clip_name, clip_path in generate_clips().items():
        print(f"{clip_name}: {clip_path} ({clip_path.stat().st_size} bytes)")