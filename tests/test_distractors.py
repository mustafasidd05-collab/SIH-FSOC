"""Unit and integration tests for distractor targets in sim/ and tracking/."""

import numpy as np
import pytest

from core.contracts import CameraState, TrackState
from sim.camera import project_target
from sim.render import RenderConfig, render
from sim.scene import (
    BeaconConfig,
    LinearMotionConfig,
    Scene,
    SceneConfig,
)
from tracking.pipeline import TrackPipeline


def test_scene_primary_target_id():
    cfg = SceneConfig(
        beacons=(
            BeaconConfig(target_id=1, range_m=1000.0, motion="linear", role="distractor"),
            BeaconConfig(target_id=2, range_m=1000.0, motion="linear", role="primary"),
            BeaconConfig(target_id=3, range_m=1000.0, motion="linear", role="distractor"),
        )
    )
    s = Scene(cfg)
    assert s.primary_target_id == 2


def test_scene_primary_target_id_default_first():
    cfg = SceneConfig(
        beacons=(
            BeaconConfig(target_id=10, range_m=1000.0, motion="linear"),
            BeaconConfig(target_id=20, range_m=1000.0, motion="linear", role="distractor"),
        )
    )
    s = Scene(cfg)
    assert s.primary_target_id == 10


def test_render_with_distractors_visible():
    cam = CameraState(
        pan_rad=0.0, tilt_rad=0.0,
        pan_min_rad=-1.0, pan_max_rad=1.0,
        tilt_min_rad=-1.0, tilt_max_rad=1.0,
        fov_h_rad=0.7, fov_v_rad=0.5,
        width_px=800, height_px=600,
    )
    cfg = SceneConfig(
        beacons=(
            BeaconConfig(
                target_id=1, range_m=1000.0, motion="linear", role="primary",
                linear=LinearMotionConfig(az0_rad=0.0, el0_rad=0.0, az_rate_rad_s=0.0, el_rate_rad_s=0.0),
                beacon_radius_px=6.0, peak_intensity=255.0,
            ),
            BeaconConfig(
                target_id=2, range_m=1000.0, motion="linear", role="distractor",
                linear=LinearMotionConfig(az0_rad=0.1, el0_rad=0.05, az_rate_rad_s=0.0, el_rate_rad_s=0.0),
                beacon_radius_px=5.0, peak_intensity=200.0,
            ),
        )
    )
    s = Scene(cfg)
    s.update_camera(cam)
    targets = s.snapshot()
    assert len(targets) == 2

    frame = render(targets, cam, frame_id=0, timestamp_s=0.0, beacon_configs=cfg.beacons)
    assert frame.image.shape == (600, 800, 3)

    px1, py1 = project_target(targets[0], cam)
    px2, py2 = project_target(targets[1], cam)
    bg_val = int(frame.image[0, 0, 0])
    assert int(frame.image[int(py1), int(px1), 0]) > bg_val + 50
    assert int(frame.image[int(py2), int(px2), 0]) > bg_val + 50


def test_pipeline_locks_onto_primary_with_distractor():
    """Verify tracking pipeline with a distractor present."""
    cam = CameraState(
        pan_rad=0.0, tilt_rad=0.0,
        pan_min_rad=-1.0, pan_max_rad=1.0,
        tilt_min_rad=-1.0, tilt_max_rad=1.0,
        fov_h_rad=0.7, fov_v_rad=0.5,
        width_px=800, height_px=600,
    )
    cfg = SceneConfig(
        beacons=(
            BeaconConfig(
                target_id=1, range_m=1000.0, motion="linear", role="primary",
                linear=LinearMotionConfig(az0_rad=0.0, el0_rad=0.0, az_rate_rad_s=0.0, el_rate_rad_s=0.0),
                beacon_radius_px=6.0, peak_intensity=255.0,
            ),
            BeaconConfig(
                target_id=2, range_m=1000.0, motion="linear", role="distractor",
                linear=LinearMotionConfig(az0_rad=0.08, el0_rad=0.0, az_rate_rad_s=0.0, el_rate_rad_s=0.0),
                beacon_radius_px=6.0, peak_intensity=180.0,
            ),
        )
    )
    s = Scene(cfg)
    pipeline = TrackPipeline()
    for i in range(15):
        s.update_camera(cam)
        targets = s.snapshot()
        frame = render(targets, cam, frame_id=i, timestamp_s=i * (1.0 / 30.0), beacon_configs=cfg.beacons)
        res = pipeline.process(frame)
        if i >= 5:
            assert res.state is TrackState.TRACK
            center_x = 800 / 2.0
            assert abs(res.centroid_px[0] - center_x) < 3.0
