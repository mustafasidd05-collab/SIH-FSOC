"""tests/test_control.py -- unit and integration tests for control/ PID and loop."""

import pytest
import numpy as np

from core.contracts import CameraState, TrackResult, TrackState
from control.pid import PID1D, PanTiltPID
from control.state_gate import is_control_active
from control.loop import ControlLoop
from sim.camera import boresight_az_el, project_azel, command_pan_tilt


def test_pid1d_step_response_and_convergence():
    """Test 1D PID step response convergence and absence of unbounded oscillation."""
    pid = PID1D(kp=0.05, ki=0.0002, kd=0.002, integral_limit=5.0, max_output_step=5.0)

    pos = 100.0  # Initial error (pixels)
    target = 0.0
    dt = 0.0333  # 30 Hz simulation timestep (33.3 ms)

    settling_time_s = None
    final_error = pos

    for step in range(300):  # 10 seconds simulation
        error = pos - target
        if settling_time_s is None and abs(error) < 1.0:
            settling_time_s = step * dt

        control_out = pid.update(error, dt)
        pos -= control_out  # Plant response (simple integrator model)
        final_error = pos - target

    assert abs(final_error) < 0.1, f"PID step response failed to converge: final error {final_error}"
    assert settling_time_s is not None and settling_time_s < 5.0, f"Settling time too long: {settling_time_s}s"
    print(f"\n[PID1D Step Response] Settling time (<1px): {settling_time_s:.3f}s | Final error: {final_error:.6f} px")


def test_pid_anti_windup_clamping():
    """Test that anti-windup prevents integral term from exceeding integral_limit."""
    integral_limit = 5.0
    pid = PID1D(kp=0.001, ki=0.01, kd=0.0, integral_limit=integral_limit)

    dt = 0.1
    large_error = 1000.0

    # Feed large error for 100 steps
    for _ in range(100):
        pid.update(large_error, dt, clamped=False)

    assert pid._integral <= integral_limit, f"Integral term {pid._integral} exceeded limit {integral_limit}"

    # Test that setting clamped=True freezes integral accumulation
    pid.reset()
    pid.update(10.0, dt, clamped=True)
    assert pid._integral == 0.0, "Integral accumulated while clamped=True"


def test_state_gating():
    """Test that control is only active during TRACK and REACQUIRE."""
    assert not is_control_active(TrackState.SEARCH)
    assert not is_control_active(TrackState.ACQUIRE)
    assert not is_control_active(TrackState.LOST)
    assert is_control_active(TrackState.TRACK)
    assert is_control_active(TrackState.REACQUIRE)

    loop = ControlLoop()
    camera = CameraState(
        pan_rad=0.0,
        tilt_rad=0.0,
        pan_min_rad=-1.0,
        pan_max_rad=1.0,
        tilt_min_rad=-1.0,
        tilt_max_rad=1.0,
        fov_h_rad=0.5,
        fov_v_rad=0.5,
        width_px=640,
        height_px=480,
    )

    track_res_search = TrackResult(
        frame_id=1,
        timestamp_s=0.033,
        state=TrackState.SEARCH,
        centroid_px=(400.0, 100.0),
        bbox_px=(390.0, 90.0, 20.0, 20.0),
        confidence=0.0,
        error_px=(80.0, -140.0),
    )

    cam_out, clamp = loop.step(track_res_search, camera, dt=0.033)
    assert cam_out.pan_rad == 0.0 and cam_out.tilt_rad == 0.0, "SEARCH produced non-zero camera movement!"


def test_closed_loop_sign_convention_negative_y():
    """Integration test: Verify camera pan/tilt moves to reduce error for negative error_px.y (target above center)."""
    camera = CameraState(
        pan_rad=0.0,
        tilt_rad=0.0,
        pan_min_rad=-1.57,
        pan_max_rad=1.57,
        tilt_min_rad=-1.57,
        tilt_max_rad=1.57,
        fov_h_rad=0.5,
        fov_v_rad=0.5,
        width_px=640,
        height_px=480,
    )

    loop = ControlLoop()

    # Target in world space: az = +0.05 rad (right), el = +0.03 rad (above)
    target_az_abs = 0.05
    target_el_abs = 0.03

    current_cam = camera
    dt = 0.033

    initial_error_px = None
    final_error_px = None

    for step in range(100):
        # 1. Compute target pixel projection on current camera frame
        az_rel, el_rel = boresight_az_el(target_az_abs, target_el_abs, current_cam.pan_rad, current_cam.tilt_rad)
        px, py = project_azel(az_rel, el_rel, current_cam)

        err_x = px - current_cam.width_px / 2.0
        err_y = py - current_cam.height_px / 2.0
        err_tuple = (err_x, err_y)

        if step == 0:
            initial_error_px = err_tuple
            # Verify setup assumption: target above center -> py < height/2 -> err_y < 0
            assert err_x > 0, f"Expected positive x error, got {err_x}"
            assert err_y < 0, f"Expected negative y error (target above center), got {err_y}"

        track_res = TrackResult(
            frame_id=step,
            timestamp_s=step * dt,
            state=TrackState.TRACK,
            centroid_px=(px, py),
            bbox_px=(px - 5, py - 5, 10, 10),
            confidence=0.95,
            error_px=err_tuple,
        )

        current_cam, _ = loop.step(track_res, current_cam, dt)
        final_error_px = err_tuple

    # Confirm errors shrank in magnitude
    assert abs(final_error_px[0]) < abs(initial_error_px[0]), f"Pan error failed to decrease! {initial_error_px[0]} -> {final_error_px[0]}"
    assert abs(final_error_px[1]) < abs(initial_error_px[1]), f"Tilt error (negative y) failed to decrease! {initial_error_px[1]} -> {final_error_px[1]}"
    assert current_cam.pan_rad > 0.0, "Pan failed to rotate right (+pan)!"
    assert current_cam.tilt_rad > 0.0, "Tilt failed to rotate up (+tilt)!"

    print(f"\n[Closed Loop Sign Test] Initial error: {initial_error_px} | Final error: {final_error_px}")
    print(f"Cam pose after 100 steps: pan={current_cam.pan_rad:.4f} rad, tilt={current_cam.tilt_rad:.4f} rad")
