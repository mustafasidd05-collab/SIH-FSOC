"""ui/mock_telemetry.py -- Mock telemetry source for UI testing and offscreen runs.

Emits TelemetryPacket and procedurally generated numpy BGR frame at 30 Hz.
State schedule: SEARCH -> ACQUIRE -> TRACK -> LOST -> REACQUIRE -> TRACK -> repeat.
Injectable time_scale allows fast automated testing.
"""

from __future__ import annotations

import math
from typing import List, Tuple
import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from core.contracts import TelemetryPacket, TrackState


class MockTelemetrySource(QObject):
    """Generates synthetic telemetry packets and pure numpy frames at 30 Hz."""

    # Emits (TelemetryPacket, np.ndarray BGR image)
    telemetry_updated = Signal(object, object)

    def __init__(
        self,
        width_px: int = 640,
        height_px: int = 480,
        time_scale: float = 1.0,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.width_px = width_px
        self.height_px = height_px
        self.time_scale = time_scale

        self._frame_id = 0
        self._sim_time_s = 0.0
        self._dt_nominal = 1.0 / 30.0  # 30 Hz

        # State schedule configuration: (state, duration_in_sim_seconds)
        self.schedule: List[Tuple[TrackState, float]] = [
            (TrackState.SEARCH, 2.0),
            (TrackState.ACQUIRE, 1.5),
            (TrackState.TRACK, 4.0),
            (TrackState.LOST, 2.0),
            (TrackState.REACQUIRE, 1.5),
            (TrackState.TRACK, 4.0),
        ]
        self._schedule_idx = 0
        self._state_start_time_s = 0.0

        # Lookback buffer for lock fraction calculation
        self._recent_states: List[TrackState] = []
        self._max_lookback = 90  # 3 seconds @ 30 Hz

        self._acq_start_time_s: float | None = None
        self._acq_completed_time_s: float = float("nan")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_timer_tick)

    @property
    def current_state(self) -> TrackState:
        return self.schedule[self._schedule_idx][0]

    def start(self) -> None:
        """Start emitting telemetry packets at 30 Hz (adjusted by time_scale)."""
        interval_ms = int(max(1.0, (1000.0 / 30.0) / self.time_scale))
        self.timer.start(interval_ms)

    def stop(self) -> None:
        """Stop emitting telemetry packets."""
        self.timer.stop()

    def set_time_scale(self, scale: float) -> None:
        """Update time scale and adjust timer interval if running."""
        self.time_scale = max(0.01, scale)
        if self.timer.isActive():
            self.start()

    def step(self) -> Tuple[TelemetryPacket, np.ndarray]:
        """Manually step 1 frame forward and return (TelemetryPacket, image)."""
        dt = self._dt_nominal * self.time_scale
        self._sim_time_s += dt
        self._frame_id += 1

        # Check schedule progression
        state, duration = self.schedule[self._schedule_idx]
        if self._sim_time_s - self._state_start_time_s >= duration:
            self._schedule_idx = (self._schedule_idx + 1) % len(self.schedule)
            self._state_start_time_s = self._sim_time_s
            new_state = self.schedule[self._schedule_idx][0]

            if new_state == TrackState.SEARCH:
                self._acq_start_time_s = self._sim_time_s
                self._acq_completed_time_s = float("nan")
            elif new_state == TrackState.TRACK and self._acq_start_time_s is not None:
                if math.isnan(self._acq_completed_time_s):
                    self._acq_completed_time_s = self._sim_time_s - self._acq_start_time_s

        current_state = self.current_state

        # Update lock fraction buffer
        self._recent_states.append(current_state)
        if len(self._recent_states) > self._max_lookback:
            self._recent_states.pop(0)

        track_count = sum(1 for s in self._recent_states if s == TrackState.TRACK)
        lock_fraction = track_count / len(self._recent_states)

        # Target motion geometry
        cx_nominal = self.width_px / 2.0
        cy_nominal = self.height_px / 2.0

        if current_state in (TrackState.TRACK, TrackState.ACQUIRE, TrackState.REACQUIRE):
            # Beacon near center with smooth wobble
            radius = 35.0 if current_state == TrackState.TRACK else 80.0
            bx = cx_nominal + radius * math.cos(2.0 * self._sim_time_s)
            by = cy_nominal + radius * math.sin(1.5 * self._sim_time_s)
            err_x = bx - cx_nominal
            err_y = by - cy_nominal
        elif current_state == TrackState.SEARCH:
            # Sweeping across frame
            bx = cx_nominal + 180.0 * math.sin(4.0 * self._sim_time_s)
            by = cy_nominal + 120.0 * math.cos(3.0 * self._sim_time_s)
            err_x = bx - cx_nominal
            err_y = by - cy_nominal
        else:  # LOST
            # Beacon missing / off frame
            bx = -100.0
            by = -100.0
            err_x = 999.0
            err_y = 999.0

        # Angles in radians (approx focal length)
        f_px = 800.0
        err_az_rad = math.atan2(err_x, f_px) if current_state != TrackState.LOST else 0.0
        err_el_rad = math.atan2(err_y, f_px) if current_state != TrackState.LOST else 0.0

        packet = TelemetryPacket(
            frame_id=self._frame_id,
            timestamp_s=self._sim_time_s,
            fps=30.0 + 0.5 * math.sin(self._sim_time_s),
            track_state=current_state,
            error_px=(err_x, err_y),
            error_az_rad=err_az_rad,
            error_el_rad=err_el_rad,
            lock_fraction=lock_fraction,
            acquisition_time_s=self._acq_completed_time_s,
            loop_time_s=0.0031 + 0.0002 * math.cos(self._sim_time_s),
        )

        # Procedural pure numpy frame generation (uint8 BGR)
        image = self._render_numpy_frame(bx, by, current_state)

        return packet, image

    def _render_numpy_frame(
        self, bx: float, by: float, state: TrackState
    ) -> np.ndarray:
        """Render a synthetic camera frame using pure numpy arrays (no OpenCV)."""
        w, h = self.width_px, self.height_px

        # Base dark background
        img = np.full((h, w, 3), (15, 13, 10), dtype=np.uint8)

        # Grid lines (reticle background)
        img[h // 2, :, :] = (35, 30, 25)
        img[:, w // 2, :] = (35, 30, 25)

        if state != TrackState.LOST and 0 <= bx < w and 0 <= by < h:
            # Gaussian spot for optical beacon
            yy, xx = np.ogrid[:h, :w]
            dist_sq = (xx - bx) ** 2 + (yy - by) ** 2

            sigma = 6.0 if state == TrackState.TRACK else 10.0
            spot = np.exp(-dist_sq / (2.0 * sigma**2))

            # Beacon color by state: BGR uint8
            if state == TrackState.TRACK:
                color = np.array([118, 230, 0], dtype=np.float32)  # #00E676 Green
            elif state == TrackState.ACQUIRE:
                color = np.array([207, 197, 57], dtype=np.float32)  # #39C5CF Cyan
            elif state == TrackState.REACQUIRE:
                color = np.array([255, 124, 181], dtype=np.float32) # #B57CFF Violet
            else:
                color = np.array([0, 179, 255], dtype=np.float32)  # #FFB300 Amber

            blob_rgb = (spot[:, :, None] * 240.0).clip(0, 255).astype(np.uint8)
            img = np.maximum(img, blob_rgb)

        return img

    def _on_timer_tick(self) -> None:
        packet, image = self.step()
        self.telemetry_updated.emit(packet, image)
