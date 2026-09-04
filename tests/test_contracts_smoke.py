"""Smoke test for core/contracts.py -- no simulation logic here, this file proves
the toolchain works (imports, dataclasses, enum, frozen semantics) against known
synthetic values."""

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from core.contracts import CameraState, SimFrame, TargetState, TelemetryPacket, TrackResult, TrackState


def _camera() -> CameraState:
    return CameraState(
        pan_rad=-0.2,
        tilt_rad=0.1,
        pan_min_rad=-1.5,
        pan_max_rad=1.5,
        tilt_min_rad=-0.5,
        tilt_max_rad=0.5,
        fov_h_rad=0.7,
        fov_v_rad=0.5,
        width_px=1280,
        height_px=720,
    )


def test_camera_state_fields():
    cam = _camera()
    assert cam.pan_min_rad <= cam.pan_rad <= cam.pan_max_rad
    assert cam.tilt_min_rad <= cam.tilt_rad <= cam.tilt_max_rad
    assert cam.fov_h_rad > 0 and cam.fov_v_rad > 0
    assert cam.width_px == 1280 and cam.height_px == 720


def test_sim_frame_carries_image_and_camera():
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame = SimFrame(frame_id=0, timestamp_s=0.0, image=img, camera=_camera())
    assert frame.image.shape == (720, 1280, 3)
    assert frame.image is img
    assert frame.camera.width_px == 1280


def test_target_state_roundtrip():
    t = TargetState(
        target_id=1,
        world_pos=(10.0, 5.0, 100.0),
        az_rad=0.1,
        el_rad=0.05,
        range_m=100.0,
        visible=True,
    )
    assert t.world_pos == (10.0, 5.0, 100.0)
    assert t.range_m > 0
    assert t.visible


def test_track_result_error_px_is_boresight_offset():
    # Centroid exactly at frame center => boresight offset (0, 0).
    centered = TrackResult(
        frame_id=0,
        timestamp_s=0.0,
        state=TrackState.TRACK,
        centroid_px=(640.0, 360.0),
        bbox_px=(600.0, 320.0, 80.0, 80.0),
        confidence=0.95,
        error_px=(640.0 - 640.0, 360.0 - 360.0),
    )
    assert centered.error_px == (0.0, 0.0)
    # Centroid 100 px right of boresight => error_px = (100, 0), not raw pixel coords.
    right = TrackResult(
        frame_id=1,
        timestamp_s=0.0,
        state=TrackState.TRACK,
        centroid_px=(740.0, 360.0),
        bbox_px=(700.0, 320.0, 80.0, 80.0),
        confidence=0.9,
        error_px=(740.0 - 640.0, 360.0 - 360.0),
    )
    assert right.error_px == (100.0, 0.0)


def test_telemetry_packet_ranges():
    p = TelemetryPacket(
        frame_id=0,
        timestamp_s=0.0,
        fps=60.0,
        track_state=TrackState.ACQUIRE,
        error_px=(3.0, -2.0),
        error_az_rad=0.01,
        error_el_rad=0.005,
        lock_fraction=0.9,
        acquisition_time_s=1.2,
        loop_time_s=0.016,
    )
    assert 0.0 <= p.lock_fraction <= 1.0
    assert p.loop_time_s > 0
    assert p.track_state is TrackState.ACQUIRE


def test_enum_values_match_state_machine():
    assert [s.value for s in TrackState] == [
        "SEARCH",
        "ACQUIRE",
        "TRACK",
        "LOST",
        "REACQUIRE",
    ]


def test_contracts_are_frozen():
    with pytest.raises(FrozenInstanceError):
        _camera().pan_rad = 0.0