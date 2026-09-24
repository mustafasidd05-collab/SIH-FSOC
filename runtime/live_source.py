"""runtime/live_source.py -- Live pipeline telemetry source.

Chains sim.scene -> sim.render -> disturbance.pipeline -> tracking.pipeline -> control.loop.
Emits telemetry_updated(TelemetryPacket, np.ndarray BGR image) at 30 Hz.

Public runtime-update API (all thread-safe when called from the Qt main thread
because the QTimer callback and these setters share the same thread):

    set_motion_pattern(pattern)          -- "linear" | "sinusoidal" | "lissajous" | "spiral"
    set_target_speed(speed_m_s)          -- 0.1 – 100 m/s → converted to az_rate_rad_s
    set_target_size(radius_px)           -- Gaussian beacon blob radius in pixels
    set_disturbance_levels(vib, turb, noise_snr_db)
    set_pid_gains(kp, ki, kd, max_step)  -- live PID gain update; resets integral
    toggle_decoy(enabled)                -- spawn / remove a dim distractor beacon
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import List
import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from core.contracts import CameraState, SimFrame, TelemetryPacket, TrackState
from core.camera.input_adapter import VideoInputAdapter
from control.loop import ControlLoop
from disturbance.pipeline import DisturbancePipeline, DisturbanceProfile, make_pipeline
from sim.render import RenderConfig, render
from sim.scene import (
    BeaconConfig,
    LinearMotionConfig,
    Scene,
    SceneConfig,
    SinusoidalMotionConfig,
    SpiralMotionConfig,
)
from tracking.pipeline import TrackPipeline

# ---------------------------------------------------------------------------
# Default scene / disturbance parameters (mirrors default_config.yaml)
# ---------------------------------------------------------------------------
_DEFAULT_RANGE_M: float = 1000.0
_DEFAULT_SPEED_M_S: float = 15.0
_DEFAULT_BEACON_RADIUS_PX: float = 6.0
_DEFAULT_VIB_SIGMA: float = 0.4       # mild profile
_DEFAULT_TURB_SIGMA: float = 0.4      # mild profile
_DEFAULT_NOISE_SNR_DB: float = 35.0   # mild profile


class LiveTelemetrySource(QObject):
    """Live telemetry source running closed-loop simulation pipeline."""

    # Emits (TelemetryPacket, np.ndarray BGR image)
    telemetry_updated = Signal(object, object)

    def __init__(
        self,
        width_px: int = 640,
        height_px: int = 480,
        time_scale: float = 1.0,
        seed: int | None = None,
        video_path: str | Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.width_px = width_px
        self.height_px = height_px
        self.time_scale = time_scale

        self._frame_id = 0
        self._sim_time_s = 0.0
        self._dt_nominal = 1.0 / 60.0  # 60 Hz

        # ---- Scene state parameters (used by _rebuild_scene) ----
        self._motion_pattern: str = "linear"
        self._target_speed_m_s: float = _DEFAULT_SPEED_M_S
        self._target_size_px: float = _DEFAULT_BEACON_RADIUS_PX
        self._decoy_enabled: bool = False

        # ---- Disturbance state parameters (used by _rebuild_disturbance) ----
        self._vib_sigma: float = _DEFAULT_VIB_SIGMA
        self._turb_sigma: float = _DEFAULT_TURB_SIGMA
        self._noise_snr_db: float = _DEFAULT_NOISE_SNR_DB

        # Initial camera state
        self.current_camera = CameraState(
            pan_rad=0.0,
            tilt_rad=0.0,
            pan_min_rad=-1.57,
            pan_max_rad=1.57,
            tilt_min_rad=-1.57,
            tilt_max_rad=1.57,
            fov_h_rad=0.5,
            fov_v_rad=0.5,
            width_px=width_px,
            height_px=height_px,
        )

        self.video_adapter = VideoInputAdapter(video_path, camera=self.current_camera, loop=True) if video_path else None
        if self.video_adapter is not None:
            self._dt_nominal = 1.0 / self.video_adapter.fps_val

        if self.video_adapter is None:
            self._rebuild_scene()
            self._rebuild_disturbance()
        else:
            self.scene = None
            self.disturbance_pipeline = None

        self.tracking_pipeline = TrackPipeline()
        self.control_loop = ControlLoop()

        # Telemetry aggregation states
        self._recent_states: List[TrackState] = []
        self._max_lookback = 180  # 3 seconds @ 60 Hz
        self._acq_start_time_s: float | None = None
        self._acq_completed_time_s: float = float("nan")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_timer_tick)

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def start(self) -> None:
        """Start live telemetry generator at 60 Hz (scaled by time_scale)."""
        interval_ms = int((self._dt_nominal / self.time_scale) * 1000.0)
        self.timer.start(max(1, interval_ms))

    def stop(self) -> None:
        """Stop live telemetry generator."""
        self.timer.stop()

    def shutdown(self) -> None:
        """Stop updates and release an external video handle, if present."""
        self.stop()
        if self.video_adapter is not None:
            self.video_adapter.release()

    def select_target(self, centroid_px: tuple[float, float]) -> None:
        """Bias the next acquisition toward a selected image coordinate."""
        self.tracking_pipeline.select_target(centroid_px)

    # -----------------------------------------------------------------------
    # Public runtime-update API — all safe to call from the Qt main thread
    # -----------------------------------------------------------------------

    def set_motion_pattern(self, pattern: str) -> None:
        """Switch target motion trajectory.

        Supported patterns (case-insensitive):
            "linear"      -- constant-velocity straight line
            "sinusoidal"  -- single-axis sinusoidal sweep
            "lissajous"   -- dual-axis Lissajous figure-8 (1:2 frequency ratio)
            "spiral"      -- outward Archimedean spiral

        Rebuilds the scene immediately; the scene clock resets to 0 so the
        tracker transitions back through SEARCH -> ACQUIRE -> TRACK.
        """
        normalised = pattern.lower().strip()
        valid = {"linear", "sinusoidal", "lissajous", "spiral"}
        if normalised not in valid:
            raise ValueError(f"Unknown motion pattern {pattern!r}. Choose from {sorted(valid)}.")
        self._motion_pattern = normalised
        self._rebuild_scene()

    def set_target_speed(self, speed_m_s: float) -> None:
        """Update target velocity (m/s at range_m=1000 m → angular rate rad/s).

        Rebuilds scene geometry; tracker re-acquires the faster/slower target.
        """
        self._target_speed_m_s = max(0.1, float(speed_m_s))
        self._rebuild_scene()

    def set_target_size(self, radius_px: float) -> None:
        """Update the Gaussian blob radius used when rendering the beacon (px).

        Takes effect on the next rendered frame with no scene rebuild needed.
        """
        self._target_size_px = max(1.0, float(radius_px))

    def set_disturbance_levels(
        self,
        vib_sigma_px: float,
        turb_sigma_px: float,
        noise_snr_db: float,
    ) -> None:
        """Update disturbance model intensities live.

        Parameters
        ----------
        vib_sigma_px : float
            Ornstein-Uhlenbeck platform-vibration std in pixels (0 = off).
        turb_sigma_px : float
            Gaussian PSF blur sigma for atmospheric turbulence in pixels (0 = off).
        noise_snr_db : float
            Sensor SNR in dB (higher = cleaner; 35=mild, 22=moderate, 12=severe).
        """
        self._vib_sigma = max(0.0, float(vib_sigma_px))
        self._turb_sigma = max(0.0, float(turb_sigma_px))
        self._noise_snr_db = max(6.0, float(noise_snr_db))
        self._rebuild_disturbance()

    def set_pid_gains(
        self,
        kp: float,
        ki: float,
        kd: float,
        max_output_step: float,
    ) -> None:
        """Update PID gains on both pan and tilt axes and reset integral state.

        Parameters
        ----------
        kp : float   Proportional gain (rad/px).
        ki : float   Integral gain (rad/(px·s)).
        kd : float   Derivative gain (rad·s/px).
        max_output_step : float  Per-frame slew-rate limit (rad/step).
        """
        pid = self.control_loop.pid
        for axis_pid in (pid.pan_pid, pid.tilt_pid):
            axis_pid.kp = float(kp)
            axis_pid.ki = float(ki)
            axis_pid.kd = float(kd)
            axis_pid.max_output_step = float(max_output_step)
        # Reset integral + derivative history so old wind-up doesn't spike on gain change
        self.control_loop.reset()

    def toggle_decoy(self, enabled: bool) -> None:
        """Spawn or remove a dim distractor beacon in the virtual scene.

        When enabled, a secondary beacon with peak_intensity=100 (vs 255 for the
        primary) and radius 4 px moves on a linear trajectory offset from the
        primary. The tracker's AI filter and confidence gating should correctly
        lock onto the brighter primary.
        """
        self._decoy_enabled = bool(enabled)
        self._rebuild_scene()

    # -----------------------------------------------------------------------
    # Internal rebuild helpers
    # -----------------------------------------------------------------------

    def _rebuild_scene(self) -> None:
        """Reconstruct Scene from current motion pattern, speed, size, and decoy state.

        Resets the scene clock to 0 so the tracker must re-acquire.  Called
        from __init__ and from every set_* method that changes scene geometry.
        Video-mode sources skip this (scene is not used there).
        """
        if self.video_adapter is not None:
            return

        range_m = _DEFAULT_RANGE_M
        az_rate = self._target_speed_m_s / range_m  # rad/s at 1000 m range

        pattern = self._motion_pattern
        if pattern == "linear":
            primary = BeaconConfig(
                target_id=1,
                range_m=range_m,
                motion="linear",
                linear=LinearMotionConfig(
                    az0_rad=0.0,
                    el0_rad=0.0,
                    az_rate_rad_s=az_rate,
                    el_rate_rad_s=-az_rate * 0.5,
                    sweep_range_rad=0.22,   # ±12.6° bounded corridor
                ),
            )
        elif pattern == "sinusoidal":
            primary = BeaconConfig(
                target_id=1,
                range_m=range_m,
                motion="sinusoidal",
                sinusoidal=SinusoidalMotionConfig(
                    az0_rad=0.0,
                    el0_rad=0.0,
                    az_amp_rad=min(0.12, az_rate * 8),
                    az_freq_hz=max(0.05, az_rate * 1.5),
                    az_phase_rad=0.0,
                    el_amp_rad=0.0,
                    el_freq_hz=0.0,
                    el_phase_rad=0.0,
                ),
            )
        elif pattern == "lissajous":
            amp = min(0.10, az_rate * 6)
            freq = max(0.05, az_rate * 1.2)
            primary = BeaconConfig(
                target_id=1,
                range_m=range_m,
                motion="sinusoidal",
                sinusoidal=SinusoidalMotionConfig(
                    az0_rad=0.0,
                    el0_rad=0.0,
                    az_amp_rad=amp,
                    az_freq_hz=freq,
                    az_phase_rad=0.0,
                    el_amp_rad=amp * 0.6,
                    el_freq_hz=freq * 2.0,         # 1:2 ratio → figure-8
                    el_phase_rad=math.pi / 2,
                ),
            )
        elif pattern == "spiral":
            primary = BeaconConfig(
                target_id=1,
                range_m=range_m,
                motion="spiral",
                spiral=SpiralMotionConfig(
                    az0_rad=0.0,
                    el0_rad=0.0,
                    omega_rad_s=az_rate * 8,
                    expansion_rate_rad_s=az_rate * 0.4,
                ),
            )
        else:  # pragma: no cover
            raise AssertionError(f"Unexpected motion pattern: {pattern!r}")

        beacons: list[BeaconConfig] = [primary]

        if self._decoy_enabled:
            decoy = BeaconConfig(
                target_id=2,
                range_m=range_m,
                motion="linear",
                role="distractor",
                beacon_radius_px=4.0,
                peak_intensity=100.0,  # dimmer than primary (255)
                linear=LinearMotionConfig(
                    az0_rad=0.06,
                    el0_rad=-0.02,
                    az_rate_rad_s=az_rate * 0.7,
                    el_rate_rad_s=az_rate * 0.3,
                ),
            )
            beacons.append(decoy)

        self.scene = Scene(SceneConfig(beacons=tuple(beacons)))

    def _rebuild_disturbance(self) -> None:
        """Reconstruct DisturbancePipeline from current disturbance level parameters.

        Cloud occlusion is kept at zero clouds (opacity=0) in the custom profile
        because it is controlled separately via the UI profile preset.
        """
        if self.video_adapter is not None:
            return

        scint = min(0.35, self._turb_sigma * 0.12)  # scale scintillation with blur
        profile = DisturbanceProfile(
            name="custom",
            turbulence={"blur_sigma_px": self._turb_sigma, "scint_sigma": max(0.01, scint)},
            occlusion={"num_clouds": 0, "speed_px_s": 40.0, "opacity": 0.0, "size_px": 60.0},
            camera_motion_blur={"blur_gain": 5.0, "max_kernel_size": 5},
            vibration={"displacement_sigma_px": self._vib_sigma, "tau_s": 0.2},
            sensor_noise={"snr_db": self._noise_snr_db, "read_noise_fraction": 0.30},
        )
        self.disturbance_pipeline = DisturbancePipeline(profile)

    def apply_disturbance_profile(self, profile_name: str) -> None:
        """Apply a named preset profile (\"mild\" | \"moderate\" | \"severe\").

        Overwrites the individual vib/turb/noise parameters to match the preset,
        then rebuilds the pipeline.
        """
        from disturbance.pipeline import PROFILES
        if profile_name not in PROFILES:
            raise KeyError(f"Unknown profile {profile_name!r}. Choose from {sorted(PROFILES)}.")
        p = PROFILES[profile_name]
        self._vib_sigma = p.vibration.get("displacement_sigma_px", _DEFAULT_VIB_SIGMA)
        self._turb_sigma = p.turbulence.get("blur_sigma_px", _DEFAULT_TURB_SIGMA)
        self._noise_snr_db = p.sensor_noise.get("snr_db", _DEFAULT_NOISE_SNR_DB)
        if self.video_adapter is None:
            self.disturbance_pipeline = make_pipeline(profile_name)

    # -----------------------------------------------------------------------
    # Frame step
    # -----------------------------------------------------------------------

    def step(self) -> tuple[TelemetryPacket, np.ndarray]:
        """Execute one simulation frame step and return (TelemetryPacket, image)."""
        t0 = time.perf_counter()
        dt = self._dt_nominal * self.time_scale

        if self.video_adapter is not None:
            sim_frame = self.video_adapter.read_frame()
            disturbed_frame = sim_frame or SimFrame(
                self._frame_id,
                self._sim_time_s,
                np.zeros((self.height_px, self.width_px, 3), dtype=np.uint8),
                self.current_camera,
            )
            self._sim_time_s = disturbed_frame.timestamp_s
        else:
            # 1. Advance scene clock
            self.scene.step(dt)
            self.scene.update_camera(self.current_camera)
            targets = self.scene.snapshot()

            # 2. Render sim frame — use dynamic beacon radius and pass beacon_configs
            #    so distractors render with their per-beacon radius/intensity overrides.
            clean_frame = render(
                targets=targets,
                camera=self.current_camera,
                frame_id=self._frame_id,
                timestamp_s=self.scene.t_s,
                config=RenderConfig(beacon_radius_px=self._target_size_px),
                beacon_configs=list(self.scene.beacon_configs),
            )

            # 3. Disturbance pipeline
            disturbed_frame = self.disturbance_pipeline.apply(clean_frame)
            self._sim_time_s = self.scene.t_s

        # 4. Tracking pipeline
        track_result = self.tracking_pipeline.process(disturbed_frame)

        # 5. Control loop step
        self.current_camera, clamp_report = self.control_loop.step(
            track_result=track_result,
            camera=self.current_camera,
            dt=dt,
        )

        # 6. Aggregate telemetry metrics
        self._frame_id += 1

        self._recent_states.append(track_result.state)
        if len(self._recent_states) > self._max_lookback:
            self._recent_states.pop(0)

        track_count = sum(
            1 for s in self._recent_states if s in (TrackState.TRACK, TrackState.REACQUIRE)
        )
        lock_fraction = track_count / len(self._recent_states) if self._recent_states else 0.0

        if track_result.state == TrackState.SEARCH and self._acq_start_time_s is None:
            self._acq_start_time_s = self._sim_time_s
        elif track_result.state == TrackState.TRACK and math.isnan(self._acq_completed_time_s):
            if self._acq_start_time_s is not None:
                self._acq_completed_time_s = self._sim_time_s - self._acq_start_time_s
            else:
                self._acq_completed_time_s = self._sim_time_s

        loop_time_s = time.perf_counter() - t0
        fps = 1.0 / self._dt_nominal

        err_x, err_y = track_result.error_px
        if self.video_adapter is not None:
            # Arbitrary external videos have no calibrated angular mapping.
            err_az_rad = 0.0
            err_el_rad = 0.0
        else:
            err_az_rad = (err_x / self.width_px) * self.current_camera.fov_h_rad if not math.isnan(err_x) else float("nan")
            err_el_rad = (err_y / self.height_px) * self.current_camera.fov_v_rad if not math.isnan(err_y) else float("nan")

        packet = TelemetryPacket(
            frame_id=self._frame_id,
            timestamp_s=self._sim_time_s,
            fps=fps,
            track_state=track_result.state,
            error_px=track_result.error_px,
            error_az_rad=err_az_rad,
            error_el_rad=err_el_rad,
            lock_fraction=lock_fraction,
            acquisition_time_s=self._acq_completed_time_s,
            loop_time_s=loop_time_s,
        )

        return packet, disturbed_frame.image

    def _on_timer_tick(self) -> None:
        packet, img = self.step()
        self.telemetry_updated.emit(packet, img)
