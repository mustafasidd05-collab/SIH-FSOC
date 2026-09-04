"""tracking/pipeline.py -- ties detection -> Kalman -> state machine together.

The only entry point the rest of the simulator needs: frame in (a SimFrame),
TrackResult out. Per frame we (1) run the stateless detector, (2) advance the
Kalman prediction with the true inter-frame dt, (3) let the state machine
decide accept/update/transition, and (4) emit the contract TrackResult.
"""

from __future__ import annotations

import math

from core.contracts import SimFrame, TrackResult

from .detect import BeaconDetector
from .kalman import KalmanTracker, DT_MIN_S
from .state_machine import TrackStateMachine
from .ai_filter import AIFilter


class TrackPipeline:
    """One detector + one filter + one state machine; process() per frame."""

    def __init__(
        self,
        detector: BeaconDetector | None = None,
        kalman: KalmanTracker | None = None,
        state_machine: TrackStateMachine | None = None,
        ai_filter: AIFilter | None = None,
        use_ai_filter: bool = True,
    ) -> None:
        self._detector = detector or BeaconDetector()
        self._kalman = kalman or KalmanTracker()
        self._state_machine = state_machine or TrackStateMachine(self._kalman)
        self._ai_filter = ai_filter or AIFilter()
        self._use_ai_filter = use_ai_filter
        self._last_timestamp_s: float | None = None
        self._selected_target_px: tuple[float, float] | None = None

    @property
    def state(self) -> TrackStateMachine:
        return self._state_machine

    def select_target(self, centroid_px: tuple[float, float]) -> None:
        """Reset the tracker and bias acquisition toward a user-selected target."""
        self._state_machine.reset()
        self._selected_target_px = (float(centroid_px[0]), float(centroid_px[1]))
    def process(self, frame: SimFrame) -> TrackResult:
        """One SimFrame in, one TrackResult out (every frame, every state)."""
        candidates = self._detector.detect_candidates(frame.image)

        reference_px = self._kalman.mean_px or self._selected_target_px
        gate_radius_px = self._state_machine.gate_radius_px

        if self._use_ai_filter and candidates:
            detection = self._ai_filter.select_best_candidate(
                frame.image,
                candidates,
                reference_px=reference_px,
                gate_radius_px=gate_radius_px if reference_px is not None else None,
            )
        elif reference_px is not None and candidates:
            gated = [
                candidate
                for candidate in candidates
                if math.dist(candidate.centroid_px, reference_px) <= gate_radius_px
            ]
            detection = (
                min(gated, key=lambda candidate: math.dist(candidate.centroid_px, reference_px))
                if gated
                else None
            )
        else:
            detection = max(candidates, key=lambda candidate: candidate.confidence) if candidates else None

        if detection is not None and self._selected_target_px is not None:
            self._selected_target_px = detection.centroid_px
        if self._kalman.active:
            self._selected_target_px = None

        if self._last_timestamp_s is None:
            dt_s = DT_MIN_S  # first frame: nothing to extrapolate from
        else:
            dt_s = frame.timestamp_s - self._last_timestamp_s
        self._last_timestamp_s = frame.timestamp_s

        camera = frame.camera
        center_px = (camera.width_px / 2.0, camera.height_px / 2.0)

        return self._state_machine.step(
            detection,
            dt_s,
            frame.frame_id,
            frame.timestamp_s,
            center_px,
        )