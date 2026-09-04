"""runtime/live_source.py -- Live pipeline telemetry source.

Chains sim.scene -> sim.render -> disturbance.pipeline -> tracking.pipeline -> control.loop.
Emits telemetry_updated(TelemetryPacket, np.ndarray BGR image) at 30 Hz.
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
from disturbance.pipeline import make_pipeline
from sim.render import render
from sim.scene import BeaconConfig, LinearMotionConfig, Scene, SceneConfig
from tracking.pipeline import TrackPipeline


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
        self._dt_nominal = 1.0 / 30.0  # 30 Hz

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
            # Scene with one optical beacon starting slightly off-center
            beacon_config = BeaconConfig(
                target_id=1,
                range_m=1000.0,
                motion="linear",
                linear=LinearMotionConfig(
                    az0_rad=0.04,  # Right of center
                    el0_rad=0.03,  # Above center
                    az_rate_rad_s=0.002,
                    el_rate_rad_s=-0.001,
                ),
            )
            scene_config = SceneConfig(beacons=[beacon_config])
            self.scene = Scene(scene_config)
            self.disturbance_pipeline = make_pipeline("mild", seed=seed)
        else:
            self.scene = None
            self.disturbance_pipeline = None

        self.tracking_pipeline = TrackPipeline()
        self.control_loop = ControlLoop()

        # Telemetry aggregation states
        self._recent_states: List[TrackState] = []
        self._max_lookback = 90  # 3 seconds @ 30 Hz
        self._acq_start_time_s: float | None = None
        self._acq_completed_time_s: float = float("nan")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_timer_tick)

    def start(self) -> None:
        """Start live telemetry generator at 30 Hz (scaled by time_scale)."""
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

            # 2. Render sim frame
            clean_frame = render(
                targets=targets,
                camera=self.current_camera,
                frame_id=self._frame_id,
                timestamp_s=self.scene.t_s,
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
