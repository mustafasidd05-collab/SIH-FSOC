"""Unit tests for sim/ -- camera model, target motion, rendering.

Coordinate math is verified against hand-computed values (see the comments
inside each test): a target on boresight lands at frame center, a target at
fov/2 lands exactly at the frame edge, and a camera panning exactly onto a
target reports zero relative error.
"""

import math

import numpy as np
import pytest

from core.contracts import CameraState, SimFrame, TargetState, TrackState
from sim.camera import (
    boresight_az_el,
    command_pan_tilt,
    is_visible,
    project_azel,
    project_target,
)
from sim.render import RenderConfig, render
from sim.scene import (
    BeaconConfig,
    LinearMotionConfig,
    Scene,
    SceneConfig,
    SinusoidalMotionConfig,
)

W, H = 1280, 720
FOV_H, FOV_V = 0.7, 0.5


def _camera(
    pan: float = 0.0,
    tilt: float = 0.0,
    fov_h: float = FOV_H,
    fov_v: float = FOV_V,
    width: int = W,
    height: int = H,
) -> CameraState:
    return CameraState(
        pan_rad=pan,
        tilt_rad=tilt,
        pan_min_rad=-1.5,
        pan_max_rad=1.5,
        tilt_min_rad=-0.5,
        tilt_max_rad=0.5,
        fov_h_rad=fov_h,
        fov_v_rad=fov_v,
        width_px=width,
        height_px=height,
    )


def _azel_target(az: float, el: float, target_id: int = 1, range_m: float = 1000.0) -> TargetState:
    return TargetState(
        target_id=target_id,
        world_pos=(0.0, 0.0, 0.0),
        az_rad=az,
        el_rad=el,
        range_m=range_m,
        visible=True,
    )


# --- projection -------------------------------------------------------------


def test_projection_boresight_center():
    cam = _camera()
    px, py = project_azel(0.0, 0.0, cam)
    assert px == pytest.approx(W / 2.0)
    assert py == pytest.approx(H / 2.0)


def test_projection_fov_edge_horizontal():
    # az_rel = fov_h/2 must land exactly at px = W (edge of the frame).
    cam = _camera()
    px, _ = project_azel(FOV_H / 2.0, 0.0, cam)
    assert px == pytest.approx(W, abs=1e-9)
    px_neg, _ = project_azel(-FOV_H / 2.0, 0.0, cam)
    assert px_neg == pytest.approx(0.0, abs=1e-9)


def test_projection_fov_edge_vertical():
    # el_rel = +fov_v/2 is ABOVE boresight => pixel row 0 (top of frame).
    cam = _camera()
    _, py = project_azel(0.0, FOV_V / 2.0, cam)
    assert py == pytest.approx(0.0, abs=1e-9)
    _, py_neg = project_azel(0.0, -FOV_V / 2.0, cam)
    assert py_neg == pytest.approx(H, abs=1e-9)


def test_projection_signs_and_scale():
    cam = _camera()
    fx = (W / 2.0) / math.tan(FOV_H / 2.0)
    az_q = 0.1
    px, _ = project_azel(az_q, 0.0, cam)
    assert px == pytest.approx(W / 2.0 + fx * math.tan(az_q))
    # Positive az => pixel right of center.
    assert px > W / 2.0
    # Positive el => pixel ABOVE center (smaller row).
    _, py = project_azel(0.0, 0.1, cam)
    assert py < H / 2.0


def test_boresight_az_el_pan_matches_absolute():
    # Camera panned AND tilted exactly onto a target: both relative angles ~0.
    cam = _camera(pan=0.05, tilt=0.02)
    az_rel, el_rel = boresight_az_el(0.05, 0.02, cam.pan_rad, cam.tilt_rad)
    assert az_rel == pytest.approx(0.0, abs=1e-12)
    assert el_rel == pytest.approx(0.0, abs=1e-12)


def test_boresight_az_el_off_axis_hand_computed():
    # az_abs=0.1, pan=0.0, tilt=0.0 => az_rel must equal az_abs exactly.
    az_rel, el_rel = boresight_az_el(0.1, 0.03, 0.0, 0.0)
    assert az_rel == pytest.approx(0.1, abs=1e-12)
    assert el_rel == pytest.approx(0.03, abs=1e-12)


def test_boresight_az_el_pure_tilt_hand_computed():
    # Camera nose-up 0.3 rad, target dead ahead at el 0:
    # v_cam = R_x(0.3) * (0, 0, 1) = (0, -sin 0.3, cos 0.3)
    # so az_rel = 0 exactly and el_rel = atan2(-sin 0.3, cos 0.3) = -0.3.
    # (Pure tilt does NOT preserve az_rel exactly -- it mixes y/z -- which is
    # why this was checked by hand instead of asserted as "unchanged".)
    cam = _camera(pan=0.0, tilt=0.3)
    az_rel, el_rel = boresight_az_el(0.0, 0.0, cam.pan_rad, cam.tilt_rad)
    assert az_rel == pytest.approx(0.0, abs=1e-12)
    assert el_rel == pytest.approx(-0.3, abs=1e-12)
    # Hand-check one off-axis case as well: az 0.1, el 0.02 under +0.3 tilt.
    az_rel2, el_rel2 = boresight_az_el(0.1, 0.02, 0.0, 0.3)
    d = np.array(
        [math.cos(0.02) * math.sin(0.1), math.sin(0.02), math.cos(0.02) * math.cos(0.1)]
    )
    v_cam = np.array(
        [d[0], d[1] * math.cos(0.3) - d[2] * math.sin(0.3), d[1] * math.sin(0.3) + d[2] * math.cos(0.3)]
    )
    assert az_rel2 == pytest.approx(math.atan2(v_cam[0], v_cam[2]), abs=1e-12)
    assert el_rel2 == pytest.approx(math.atan2(v_cam[1], np.hypot(v_cam[0], v_cam[2])), abs=1e-12)


def test_boresight_az_el_behind_camera():
    # az=pi is directly behind the camera; atan2 of the same-frame case is
    # well-defined and must not blow up (no tan() anywhere in this path).
    az_rel, el_rel = boresight_az_el(math.pi, 0.0, 0.0, 0.0)
    assert az_rel == pytest.approx(math.pi, abs=1e-12)
    assert el_rel == pytest.approx(0.0, abs=1e-12)


# --- visibility ---------------------------------------------------------------


def test_visibility_in_fov_true():
    assert is_visible(0.1, 0.0, _camera())
    assert is_visible(FOV_H / 2.0, 0.0, _camera())  # exactly at edge: visible


def test_visibility_out_of_fov_false():
    assert not is_visible(FOV_H / 2.0 + 0.01, 0.0, _camera())
    assert not is_visible(0.0, FOV_V / 2.0 + 0.01, _camera())


def test_visibility_behind_camera_false():
    assert not is_visible(math.pi, 0.0, _camera())


# --- clamping ----------------------------------------------------------------


def test_command_pan_tilt_in_range_applied_verbatim():
    cam = _camera()
    out, report = command_pan_tilt(cam, 0.3, -0.2)
    assert report.pan_clamped is False and report.tilt_clamped is False
    assert out.pan_rad == pytest.approx(0.3)
    assert out.tilt_rad == pytest.approx(-0.2)
    # Original state untouched (frozen dataclass, replace-based).
    assert cam.pan_rad == pytest.approx(0.0)


def test_command_pan_tilt_clamps_out_of_range():
    cam = _camera()
    out, report = command_pan_tilt(cam, 5.0, -3.0)
    assert report.pan_clamped is True and report.tilt_clamped is True
    assert out.pan_rad == cam.pan_max_rad
    assert out.tilt_rad == cam.tilt_min_rad


def test_command_pan_tilt_at_bound_not_clamped():
    # A command exactly at the hard limit is legal: clamp must NOT be reported.
    cam = _camera()
    out, report = command_pan_tilt(cam, cam.pan_max_rad, cam.tilt_min_rad)
    assert report.pan_clamped is False and report.tilt_clamped is False
    assert out.pan_rad == cam.pan_max_rad
    assert out.tilt_rad == cam.tilt_min_rad


def test_project_target_wrapper():
    t = _azel_target(0.0, 0.0)
    cam = _camera()
    assert project_target(t, cam) == pytest.approx((W / 2.0, H / 2.0))


# --- scene motion ------------------------------------------------------------


def _linear_scene(dt_per_step: float = 0.1) -> Scene:
    return Scene(
        SceneConfig(
            beacons=(
                BeaconConfig(
                    target_id=1,
                    range_m=1000.0,
                    motion="linear",
                    linear=LinearMotionConfig(az0_rad=0.1, el0_rad=0.05, az_rate_rad_s=0.02, el_rate_rad_s=-0.01),
                ),
            )
        )
    )


def test_linear_motion_exact_analytic():
    s = _linear_scene()
    dt = 0.05
    for _ in range(20):
        s.step(dt)  # total t = 1.0 s
    assert s.t_s == pytest.approx(1.0)

    s.update_camera(_camera())
    t = s.snapshot()[0]
    # az(t) = 0.1 + 0.02*1.0, el(t) = 0.05 - 0.01*1.0 -- NO integration drift.
    assert t.az_rad == pytest.approx(0.1 + 0.02 * 1.0)
    assert t.el_rad == pytest.approx(0.05 - 0.01 * 1.0)


def test_linear_world_position_hand_computed():
    s = _linear_scene()
    s.step(10.0)  # az = 0.1 + 0.2 = 0.3, el = 0.05 - 0.1 = -0.05
    s.update_camera(_camera())
    t = s.snapshot()[0]
    r = 1000.0
    expected = (
        r * math.cos(-0.05) * math.sin(0.3),
        r * math.sin(-0.05),
        r * math.cos(-0.05) * math.cos(0.3),
    )
    assert t.world_pos == pytest.approx(expected)
    assert t.range_m == pytest.approx(r)


def test_sinusoidal_motion_quarter_period():
    s = Scene(
        SceneConfig(
            beacons=(
                BeaconConfig(
                    target_id=1,
                    range_m=500.0,
                    motion="sinusoidal",
                    sinusoidal=SinusoidalMotionConfig(
                        az0_rad=0.0,
                        el0_rad=0.0,
                        az_amp_rad=0.15,
                        az_freq_hz=2.0,
                        az_phase_rad=0.0,
                        el_amp_rad=0.1,
                        el_freq_hz=1.0,
                        el_phase_rad=0.0,
                    ),
                ),
            )
        )
    )
    # t = 1/(4*2) puts az at exactly +amp; t = 1/(4*1) puts el at exactly +amp.
    s.step(1.0 / 8.0)
    s.update_camera(_camera())
    t = s.snapshot()[0]
    assert t.az_rad == pytest.approx(0.15)
    assert t.el_rad == pytest.approx(0.1 * math.sin(math.pi / 4.0), abs=1e-9)


def test_snapshot_requires_camera():
    s = _linear_scene()
    with pytest.raises(RuntimeError):
        s.snapshot()


def test_scene_config_from_dict_flat_and_nested():
    cfg = SceneConfig.from_dict(
        {
            "beacons": [
                {"target_id": 1, "range_m": 800.0, "motion": "linear", "az0_rad": 0.1, "el0_rad": 0.0, "az_rate_rad_s": 0.01},
                {"target_id": 2, "motion": "sinusoidal", "sinusoidal": {"az0_rad": 0.0, "el0_rad": 0.0, "az_amp_rad": 0.2, "az_freq_hz": 0.5, "az_phase_rad": 0.0, "el_amp_rad": 0.1, "el_freq_hz": 0.25, "el_phase_rad": 0.0}},
            ]
        }
    )
    s = Scene(cfg)
    s.update_camera(_camera())
    assert len(s.snapshot()) == 2
    assert cfg.beacons[0].target_id == 1


# --- rendering ---------------------------------------------------------------


def test_render_frame_shape_dtype_and_camera():
    cam = _camera()
    frame = render([_azel_target(0.1, 0.05)], cam, frame_id=7, timestamp_s=0.35)
    assert isinstance(frame, SimFrame)
    assert frame.frame_id == 7
    assert frame.timestamp_s == pytest.approx(0.35)
    assert frame.image.shape == (H, W, 3)
    assert frame.image.dtype == np.uint8
    assert frame.camera is cam


def test_render_beacon_brighter_than_background():
    cam = _camera()
    px, py = project_azel(0.0, 0.0, cam)  # frame center
    frame = render([_azel_target(0.0, 0.0)], cam, frame_id=0, timestamp_s=0.0)
    center_brightness = float(frame.image[int(py), int(px)].max())
    corner_brightness = float(frame.image[0, 0].max())
    assert center_brightness > corner_brightness + 50.0
    # Background in a distant corner keeps its configured value.
    assert tuple(int(v) for v in frame.image[0, 0]) == RenderConfig().background_bgr


def test_render_invisible_target_absent():
    cam = _camera()
    hidden = TargetState(
        target_id=1,
        world_pos=(0.0, 0.0, 0.0),
        az_rad=math.pi,
        el_rad=0.0,
        range_m=1000.0,
        visible=False,  # the flag render() must honor (Scene computes it from FOV)
    )
    frame_a = render([hidden], cam, frame_id=0, timestamp_s=0.0)
    frame_b = render([], cam, frame_id=0, timestamp_s=0.0)
    assert np.array_equal(frame_a.image, frame_b.image)


def test_render_off_frame_target_absent():
    # A visible target whose projection falls outside the frame (per the FOV
    # math) must be skipped, not crash: az_rel = fov_h projects to px = 2W.
    cam = _camera()
    t = _azel_target(FOV_H, 0.0)
    frame = render([t], cam, frame_id=0, timestamp_s=0.0)
    assert frame.image.shape == (H, W, 3)
    # The beacon must NOT appear at frame edge or center -- frame is pure bg.
    assert np.array_equal(frame.image, render([], cam, frame_id=0, timestamp_s=0.0).image)