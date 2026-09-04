"""control/loop.py -- control loop tying TrackResult -> PID -> sim.camera.command_pan_tilt."""

from __future__ import annotations

import logging

from core.contracts import CameraState, TrackResult
from control.pid import PanTiltPID
from control.state_gate import is_control_active
from sim.camera import ClampReport, command_pan_tilt

logger = logging.getLogger(__name__)

__all__ = ["ControlLoop"]


class ControlLoop:
    """Closed-loop control orchestrator.

    Consumes TrackResult from tracking/ and CameraState from sim/, updates the PID
    controller when active, commands new pan/tilt angles via sim.camera.command_pan_tilt,
    and tracks saturation ClampReports.

    Design note on Slew-Rate Limiting:
        DEFAULT_MAX_OUTPUT_STEP (0.003 rad/step ~ 3.84 px/step at 30 Hz) acts as a deliberate
        slew-rate limit on commanded pan/tilt per frame. This physical gimbal velocity limit
        prevents large single-frame corrections from overshooting and driving the target outside
        the camera field of view during initial acquisition or transient noise spikes.
    """

    def __init__(self, pid: PanTiltPID | None = None) -> None:
        self.pid = pid if pid is not None else PanTiltPID()
        self.last_clamp_report = ClampReport(pan_clamped=False, tilt_clamped=False)

    def reset(self) -> None:
        """Reset PID internal states."""
        self.pid.reset()
        self.last_clamp_report = ClampReport(pan_clamped=False, tilt_clamped=False)

    def step(
        self,
        track_result: TrackResult,
        camera: CameraState,
        dt: float,
    ) -> tuple[CameraState, ClampReport]:
        """Execute one control step.

        Parameters
        ----------
        track_result : TrackResult
            Tracking state and error vector from tracking module.
        camera : CameraState
            Current camera pose and optics.
        dt : float
            Timestep in seconds.

        Returns
        -------
        tuple[CameraState, ClampReport]
            Updated camera state and joint saturation clamp report.
        """
        # State gating check
        if not is_control_active(track_result.state):
            # Reset PID so integral term does not wind up during inactive periods
            self.pid.reset()
            self.last_clamp_report = ClampReport(pan_clamped=False, tilt_clamped=False)
            return camera, self.last_clamp_report

        # Compute pan and tilt deltas from PID
        delta_pan, delta_tilt = self.pid.update(
            track_result.error_px,
            dt,
            pan_clamped=self.last_clamp_report.pan_clamped,
            tilt_clamped=self.last_clamp_report.tilt_clamped,
        )

        # Apply gimbal command with saturation limits from CameraState
        new_pan = camera.pan_rad + delta_pan
        new_tilt = camera.tilt_rad + delta_tilt

        updated_camera, clamp_report = command_pan_tilt(
            camera=camera,
            pan_cmd_rad=new_pan,
            tilt_cmd_rad=new_tilt,
        )

        if clamp_report.pan_clamped or clamp_report.tilt_clamped:
            logger.warning(
                "Control loop gimbal saturation: pan_clamped=%s, tilt_clamped=%s",
                clamp_report.pan_clamped,
                clamp_report.tilt_clamped,
            )

        self.last_clamp_report = clamp_report
        return updated_camera, clamp_report
