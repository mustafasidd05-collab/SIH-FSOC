"""tracking/state_machine.py -- the lock state machine.

SEARCH -> ACQUIRE -> TRACK -> LOST -> REACQUIRE -> TRACK

What drives every transition is a per-frame evaluation of the Detection
against (a) a confidence floor and (b) a gate around the Kalman prediction,
plus (c) consecutive-miss counting. Every threshold is a NAMED CONSTANT below
-- there are no magic numbers, and the rationale for each is stated next to
it. Misses are counted when: no detection at all, detection below the active
confidence floor, or detection outside GATE_RADIUS_PX of the prediction
(plausible-target gating -- a candidate that far from where physics says the
beacon should be is a false positive and must not feed the filter).

State roles:

SEARCH      -- scan the whole frame. Three consecutive high-confidence
               detections (FRAMES_TO_ACQUIRE) seed the Kalman filter and open
               ACQUIRE. Nothing here gates on position: we have no prior.
ACQUIRE     -- filter is seeded at the detection; confirm the target for
               FRAMES_TO_CONFIRM frames (confidence floor + gate) before
               declaring TRACK. A miss streak aborts back to SEARCH (fresh
               scan, stale filter discarded).
TRACK       -- report the smoothed centroid (error_px is only meaningful
               here, per the contract). Every accepted frame resets the miss
               counter; MAX_MISSES_BEFORE_LOST consecutive misses (~167 ms at
               60 fps) drops the lock to LOST -- we NEVER keep reporting stale
               data in TRACK.
LOST        -- the filter keeps predicting (velocity extrapolation) but is
               not updated. Candidates must clear REACQUIRE_CONFIDENCE and
               the gate FRAMES_TO_REACQUIRE times before REACQUIRE. After
               LOST_TIMEOUT_FRAMES (~3 s) without a candidate we give up on
               the trajectory and return to SEARCH, so the filter cannot
               extrapolate forever.
REACQUIRE   -- we have a gated, plausible candidate again and a living
               prediction; confirm it for FRAMES_TO_CONFIRM frames, then back
               to full TRACK. A miss streak falls back to LOST.

A TrackResult is emitted EVERY frame whatever the state. error_px is
(NaN, NaN) outside TRACK -- the contract types it as tuple[float, float] and
NaN is the standard numeric spelling of "no meaningful value"; control/ must
check `state is TrackState.TRACK` before consuming it. This rule is part of
the module contract and is tested.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from core.contracts import TrackResult, TrackState

if TYPE_CHECKING:
    from .detect import Detection
    from .kalman import KalmanTracker

# ---------------------------------------------------------------------------
# Named thresholds (the contract of this state machine). All documented where
# they bite; unit-tested transitions pin these values down.
# ---------------------------------------------------------------------------

# SEARCH-side
CONFIDENCE_TO_ACQUIRE = 0.6  # a detection must be this confident to count toward acquisition
FRAMES_TO_ACQUIRE = 3  # consecutive qualifying detections to seed + enter ACQUIRE

# ACQUIRE / REACQUIRE confirmation
CONFIDENCE_TO_CONFIRM_TRACK = 0.5  # floor for each confirmation frame
FRAMES_TO_CONFIRM = 3  # consecutive confirmed frames before TRACK
MISSES_TO_ABORT_ACQUIRE = 3  # miss streak in ACQUIRE -> back to SEARCH

# TRACK-side
TRACK_CONFIDENCE_MIN = 0.45  # in TRACK, detections below this are misses
MAX_MISSES_BEFORE_LOST = 10  # consecutive misses (~167 ms @ 60 fps) -> LOST

# Gating (used in ACQUIRE, TRACK, LOST, REACQUIRE)
GATE_RADIUS_PX = 80.0  # candidate must land within this of the prediction to be plausible

# LOST-side
REACQUIRE_CONFIDENCE = 0.55  # candidate floor while LOST (stricter than TRACK floor)
FRAMES_TO_REACQUIRE = 3  # consecutive gated candidates before REACQUIRE
MISSES_TO_ABORT_REACQUIRE = 3  # miss streak in REACQUIRE -> back to LOST
LOST_TIMEOUT_FRAMES = 180  # ~3 s @ 60 fps without a candidate -> fresh SEARCH

# Value used for centroid/bbox on frames with no detection at all (SEARCH
# with nothing to look at, or contract-required "no detection" frames).
_NO_DETECTION_CENTROID = (0.0, 0.0)
_NO_DETECTION_BBOX = (0.0, 0.0, 0.0, 0.0)


def _distance_px(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TrackStateMachine:
    """Owns the KalmanTracker and the state; drives both from per-frame
    Detections. All thresholds overridable for tests (defaults = constants)."""

    def __init__(
        self,
        kalman: "KalmanTracker",
        *,
        confidence_to_acquire: float = CONFIDENCE_TO_ACQUIRE,
        frames_to_acquire: int = FRAMES_TO_ACQUIRE,
        confidence_to_confirm_track: float = CONFIDENCE_TO_CONFIRM_TRACK,
        frames_to_confirm: int = FRAMES_TO_CONFIRM,
        misses_to_abort_acquire: int = MISSES_TO_ABORT_ACQUIRE,
        track_confidence_min: float = TRACK_CONFIDENCE_MIN,
        max_misses_before_lost: int = MAX_MISSES_BEFORE_LOST,
        gate_radius_px: float = GATE_RADIUS_PX,
        reacquire_confidence: float = REACQUIRE_CONFIDENCE,
        frames_to_reacquire: int = FRAMES_TO_REACQUIRE,
        misses_to_abort_reacquire: int = MISSES_TO_ABORT_REACQUIRE,
        lost_timeout_frames: int = LOST_TIMEOUT_FRAMES,
    ) -> None:
        self._kf = kalman
        self.state = TrackState.SEARCH

        self._conf_to_acquire = confidence_to_acquire
        self._frames_to_acquire = frames_to_acquire
        self._conf_to_confirm = confidence_to_confirm_track
        self._frames_to_confirm = frames_to_confirm
        self._misses_to_abort_acquire = misses_to_abort_acquire
        self._track_conf_min = track_confidence_min
        self._max_misses = max_misses_before_lost
        self._gate_radius = gate_radius_px
        self._reacquire_conf = reacquire_confidence
        self._frames_to_reacquire = frames_to_reacquire
        self._misses_to_abort_reacquire = misses_to_abort_reacquire
        self._lost_timeout = lost_timeout_frames

        # Running counters (per-state, reset on transition).
        self._acquire_streak = 0
        self._confirm_streak = 0
        self._miss_streak = 0
        self._track_misses = 0
        self._reacquire_streak = 0
        self._lost_frames = 0

    # -- public API ---------------------------------------------------------

    @property
    def gate_radius_px(self) -> float:
        """Spatial gate used to reject candidates far from the tracked path."""
        return self._gate_radius

    def reset(self) -> None:
        """Return to a fresh SEARCH state and discard all trajectory history."""
        self._kf.reset()
        self.state = TrackState.SEARCH
        self._acquire_streak = 0
        self._confirm_streak = 0
        self._miss_streak = 0
        self._track_misses = 0
        self._reacquire_streak = 0
        self._lost_frames = 0

    def step(
        self,
        detection: "Detection | None",
        dt_s: float,
        frame_id: int,
        timestamp_s: float,
        image_center_px: tuple[float, float],
    ) -> TrackResult:
        """Advance one frame and return the TrackResult for it."""
        if self.state is TrackState.SEARCH:
            self._step_search(detection)
        elif self.state is TrackState.ACQUIRE:
            self._step_acquire(detection, dt_s)
        elif self.state is TrackState.TRACK:
            self._step_track(detection, dt_s)
        elif self.state is TrackState.LOST:
            self._step_lost(detection, dt_s)
        elif self.state is TrackState.REACQUIRE:
            self._step_reacquire(detection, dt_s)
        else:  # pragma: no cover -- enum is closed; defensive
            raise AssertionError(f"unknown state {self.state}")

        return self._build_result(detection, frame_id, timestamp_s, image_center_px)

    # -- transitions (one method per state) -----------------------------------

    def _step_search(self, detection: "Detection | None") -> None:
        if (
            detection is not None
            and detection.confidence >= self._conf_to_acquire
        ):
            self._acquire_streak += 1
        else:
            self._acquire_streak = 0

        if self._acquire_streak >= self._frames_to_acquire:
            self._kf.initialize(detection.centroid_px)  # type: ignore[union-attr]
            self._acquire_streak = 0
            self._confirm_streak = 0
            self._miss_streak = 0
            self.state = TrackState.ACQUIRE

    def _step_acquire(self, detection: "Detection | None", dt_s: float) -> None:
        predicted = self._kf.predict(dt_s)
        accepted = self._accept(detection, self._conf_to_confirm, predicted)

        if accepted:
            self._kf.update(detection.centroid_px)  # type: ignore[union-attr]
            self._confirm_streak += 1
            self._miss_streak = 0
        else:
            self._confirm_streak = 0
            self._miss_streak += 1
            if self._miss_streak >= self._misses_to_abort_acquire:
                self._kf.reset()
                self._confirm_streak = 0
                self._miss_streak = 0
                self.state = TrackState.SEARCH
                return

        if self._confirm_streak >= self._frames_to_confirm:
            self._confirm_streak = 0
            self._track_misses = 0
            self.state = TrackState.TRACK

    def _step_track(self, detection: "Detection | None", dt_s: float) -> None:
        predicted = self._kf.predict(dt_s)
        accepted = self._accept(detection, self._track_conf_min, predicted)

        if accepted:
            self._kf.update(detection.centroid_px)  # type: ignore[union-attr]
            self._track_misses = 0
        else:
            self._track_misses += 1
            if self._track_misses >= self._max_misses:
                self._track_misses = 0
                self._reacquire_streak = 0
                self._lost_frames = 0
                self.state = TrackState.LOST

    def _step_lost(self, detection: "Detection | None", dt_s: float) -> None:
        predicted = self._kf.predict(dt_s)
        self._lost_frames += 1

        candidate = self._accept(detection, self._reacquire_conf, predicted)

        if candidate:
            self._reacquire_streak += 1
            if self._reacquire_streak >= self._frames_to_reacquire:
                self._kf.update(detection.centroid_px)  # type: ignore[union-attr]
                self._reacquire_streak = 0
                self._confirm_streak = 0
                self._miss_streak = 0
                self.state = TrackState.REACQUIRE
                return
        else:
            self._reacquire_streak = 0

        if self._lost_frames > self._lost_timeout:
            self._kf.reset()
            self._reacquire_streak = 0
            self.state = TrackState.SEARCH

    def _step_reacquire(self, detection: "Detection | None", dt_s: float) -> None:
        predicted = self._kf.predict(dt_s)
        accepted = self._accept(detection, self._conf_to_confirm, predicted)

        if accepted:
            self._kf.update(detection.centroid_px)  # type: ignore[union-attr]
            self._confirm_streak += 1
            self._miss_streak = 0
        else:
            self._confirm_streak = 0
            self._miss_streak += 1
            if self._miss_streak >= self._misses_to_abort_reacquire:
                self._miss_streak = 0
                self.state = TrackState.LOST
                return

        if self._confirm_streak >= self._frames_to_confirm:
            self._confirm_streak = 0
            self._track_misses = 0
            self.state = TrackState.TRACK

    # -- helpers --------------------------------------------------------------

    def _accept(
        self,
        detection: "Detection | None",
        confidence_floor: float,
        predicted: tuple[float, float] | None,
    ) -> bool:
        """A detection is ACCEPTED when it exists, clears the active
        confidence floor, and (while we have a filter prior) lands inside
        GATE_RADIUS_PX of the prediction."""
        if detection is None:
            return False
        if detection.confidence < confidence_floor:
            return False
        if predicted is not None and _distance_px(detection.centroid_px, predicted) > self._gate_radius:
            return False
        return True

    def _build_result(
        self,
        detection: "Detection | None",
        frame_id: int,
        timestamp_s: float,
        image_center_px: tuple[float, float],
    ) -> TrackResult:
        if detection is not None:
            bbox = detection.bbox_px
            confidence = detection.confidence
        else:
            bbox = _NO_DETECTION_BBOX
            confidence = 0.0

        filtered = self._kf.mean_px
        if filtered is not None:
            centroid: tuple[float, float] = filtered
        elif detection is not None:
            centroid = detection.centroid_px
        else:
            centroid = _NO_DETECTION_CENTROID

        if self.state is TrackState.TRACK:
            error_px: tuple[float, float] = (
                centroid[0] - image_center_px[0],
                centroid[1] - image_center_px[1],
            )
        else:
            error_px = (math.nan, math.nan)

        return TrackResult(
            frame_id=frame_id,
            timestamp_s=timestamp_s,
            state=self.state,
            centroid_px=centroid,
            bbox_px=bbox,
            confidence=confidence,
            error_px=error_px,
        )