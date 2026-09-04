"""Generate labeled CNN patches using the existing simulator and disturbances."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from core.contracts import CameraState
from disturbance.pipeline import make_pipeline
from sim.camera import project_target
from sim.render import render
from sim.scene import BeaconConfig, LinearMotionConfig, Scene, SceneConfig


PATCH_SIZE = 32


def _crop(image: np.ndarray, center: tuple[float, float]) -> np.ndarray | None:
    half = PATCH_SIZE // 2
    cx, cy = round(center[0]), round(center[1])
    if not (half <= cx < image.shape[1] - half and half <= cy < image.shape[0] - half):
        return None
    return image[cy - half : cy + half, cx - half : cx + half].copy()


def augment_patch(patch: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Apply exposure, noise, blur, and sub-pixel-shift augmentation."""
    image = patch.astype(np.float32)
    image = image * rng.uniform(0.55, 1.20) + rng.uniform(-12.0, 8.0)
    image += rng.normal(0.0, rng.uniform(0.0, 12.0), image.shape)

    if rng.random() < 0.45:
        kernel_size = int(rng.choice((3, 5, 7)))
        kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)
        if rng.random() < 0.5:
            kernel[kernel_size // 2, :] = 1.0
        else:
            kernel[:, kernel_size // 2] = 1.0
        image = cv2.filter2D(image, -1, kernel / kernel.sum())

    transform = np.float32(
        [[1.0, 0.0, rng.uniform(-2.0, 2.0)], [0.0, 1.0, rng.uniform(-2.0, 2.0)]]
    )
    image = cv2.warpAffine(
        image,
        transform,
        (PATCH_SIZE, PATCH_SIZE),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return np.clip(image, 0, 255).astype(np.uint8)


def generate_patch_dataset(
    output_dir: str | Path,
    num_samples: int = 500,
    *,
    seed: int = 42,
    disturbance_profile: str = "moderate",
) -> tuple[int, int]:
    """Write balanced positive/negative 32x32 PNG crops.

    Positives are crops of the configured primary beacon. Negatives alternate
    between rendered distractors and disturbed background, providing hard
    examples without creating a second scene generator.
    """
    if num_samples <= 0:
        raise ValueError("num_samples must be > 0")

    output = Path(output_dir)
    positive_dir = output / "positive"
    negative_dir = output / "negative"
    positive_dir.mkdir(parents=True, exist_ok=True)
    negative_dir.mkdir(parents=True, exist_ok=True)

    camera = CameraState(
        pan_rad=0.0,
        tilt_rad=0.0,
        pan_min_rad=-1.0,
        pan_max_rad=1.0,
        tilt_min_rad=-1.0,
        tilt_max_rad=1.0,
        fov_h_rad=0.7,
        fov_v_rad=0.5,
        width_px=640,
        height_px=480,
    )
    beacons = (
        BeaconConfig(
            target_id=1,
            range_m=1000.0,
            motion="linear",
            role="primary",
            beacon_radius_px=7.0,
            peak_intensity=255.0,
            linear=LinearMotionConfig(0.0, 0.0, 0.003, 0.001),
        ),
        BeaconConfig(
            target_id=2,
            range_m=1000.0,
            motion="linear",
            role="distractor",
            beacon_radius_px=4.0,
            peak_intensity=175.0,
            linear=LinearMotionConfig(0.12, 0.06, -0.001, 0.0),
        ),
        BeaconConfig(
            target_id=3,
            range_m=1000.0,
            motion="linear",
            role="distractor",
            beacon_radius_px=3.0,
            peak_intensity=220.0,
            linear=LinearMotionConfig(-0.11, -0.05, 0.001, 0.0),
        ),
    )
    scene = Scene(SceneConfig(beacons=beacons))
    disturbances = make_pipeline(disturbance_profile, seed=seed)
    rng = np.random.default_rng(seed)
    positive_count = 0
    negative_count = 0
    frame_id = 0

    while positive_count < num_samples or negative_count < num_samples:
        scene.step(1.0 / 30.0)
        scene.update_camera(camera)
        targets = scene.snapshot()
        frame = render(
            targets,
            camera,
            frame_id,
            scene.t_s,
            beacon_configs=beacons,
        )
        image = disturbances(frame).image
        projected = {target.target_id: project_target(target, camera) for target in targets if target.visible}

        if positive_count < num_samples and 1 in projected:
            patch = _crop(image, projected[1])
            if patch is not None:
                patch = augment_patch(patch, rng)
                cv2.imwrite(str(positive_dir / f"pos_{positive_count:05d}.png"), patch)
                positive_count += 1

        if negative_count < num_samples:
            distractor_id = 2 if negative_count % 2 == 0 else 3
            patch = _crop(image, projected[distractor_id]) if distractor_id in projected else None
            if patch is None:
                for _ in range(20):
                    center = (rng.uniform(20, 620), rng.uniform(20, 460))
                    if all(np.hypot(center[0] - x, center[1] - y) > 48 for x, y in projected.values()):
                        patch = _crop(image, center)
                        break
            if patch is not None:
                patch = augment_patch(patch, rng)
                cv2.imwrite(str(negative_dir / f"neg_{negative_count:05d}.png"), patch)
                negative_count += 1

        frame_id += 1
        if frame_id > num_samples * 4:
            break

    if positive_count != num_samples or negative_count != num_samples:
        raise RuntimeError(
            f"dataset generation stopped at {positive_count} positive and {negative_count} negative samples"
        )
    print(f"Dataset generated: {positive_count} positive, {negative_count} negative in {output}")
    return positive_count, negative_count


if __name__ == "__main__":
    generate_patch_dataset(Path("training/dataset"), num_samples=1000)