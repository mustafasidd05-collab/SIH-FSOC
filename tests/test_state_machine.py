"""Unit tests for tracking/state_machine.py -- the lock state machine.

The scripted-detection style makes every transition explicit: we drive the
machine with hand-built Detection objects and assert the exact state
sequence and frame indices, so the acquisition/miss/reacquisition counters
are pinned down -- not just "something eventually locks".
"""

import math

import pytest

from core.contracts import TrackResult, TrackState
from tracking.detect import Detection
from tracking.kalman import KalmanTracker
from tracking.state_machine import (
    CONFIDENCE_TO_ACQUIRE,
    FRAMES_TO_ACQUIRE,
    FRAMES_TO_CONFIRM,
    FRAMES_TO_REACQUIRE,
    MAX_MISSES_BEFORE_LOST,
    MISSES_TO_ABORT_ACQUIRE,
    TrackStateMachine,
)

CENTER = (640.0, 360.0)
DT = 1 / 60.0


def _det(conf: float, xy: tuple[float, float] = CENTER) -> Detection:
    return Detection(centroid_px=xy, bbox_px=(xy[0] - 3, xy[1] - 3, 6, 6), confidence=conf)


def _make() -> TrackStateMachine:
    return TrackStateMachine(KalmanTracker())


def _feed(sm: TrackStateMachine, dets: list[Detection | None]) -> list[TrackResult]:
    results: list[TrackResult] = []
    for i, det in enumerate(dets):
        results.append(sm.step(det, DT, i, i * DT, CENTER))
    return results


# ---------------------------------------------------------------------------


def test_happy_path_acquires_and_locks():
    sm = _make()
    dets = [_det(0.9)] * (FRAMES_TO_ACQUIRE + FRAMES_TO_CONFIRM + 2)
    results = _feed(sm, dets)

    states = [r.state for r in results]
    # 2 SEARCH (streak 1,2), 3rd frame completes streak -> ACQUIRE,
    # then FRAMES_TO_CONFIRM confirming frames -> TRACK, and it stays TRACK.
    assert states[0] is TrackState.SEARCH
    assert states[1] is TrackState.SEARCH
    assert states[2] is TrackState.ACQUIRE
    assert states[FRAMES_TO_ACQUIRE - 1 + FRAMES_TO_CONFIRM] is TrackState.TRACK
    assert states[-1] is TrackState.TRACK
    assert TrackState.TRACK in states


def test_low_confidence_never_acquires():
    sm = _make()
    results = _feed(sm, [_det(CONFIDENCE_TO_ACQUIRE - 0.05)] * 20)
    assert all(r.state is TrackState.SEARCH for r in results)


def test_misses_drop_lock_after_max_misses_not_silently():
    sm = _make()
    dets = [_det(0.9)] * (FRAMES_TO_ACQUIRE + FRAMES_TO_CONFIRM)  # -> TRACK at last frame
    results = _feed(sm, dets)

    assert results[-1].state is TrackState.TRACK

    # Now MAX_MISSES_BEFORE_LOST consecutive misses. There is no detection at
    # all (None): the machine must count and drop to LOST exactly at the
    # MAX_MISSES_BEFORE_LOST-th miss, and NOT keep reporting TRACK afterwards.
    miss_results: list[TrackResult] = []
    k = len(dets)
    for _ in range(MAX_MISSES_BEFORE_LOST):
        miss_results.append(sm.step(None, DT, k, k * DT, CENTER))
        k += 1

    assert miss_results[MAX_MISSES_BEFORE_LOST - 1].state is TrackState.LOST
    # While the miss streak was below the threshold the machine may still
    # *report* TRACK (prediction bridges brief gaps), but once LOST fires it
    # must stay out of TRACK on a follow-up miss.
    following = sm.step(None, DT, k, k * DT, CENTER)
    assert following.state is not TrackState.TRACK


def test_lost_reacquire_track_cycle():
    sm = _make()
    dets = [_det(0.9)] * (FRAMES_TO_ACQUIRE + FRAMES_TO_CONFIRM)
    _feed(sm, dets)  # locked at end
    k = len(dets)

    # Miss until LOST.
    for _ in range(MAX_MISSES_BEFORE_LOST):
        sm.step(None, DT, k, k * DT, CENTER)
        k += 1
    assert sm.state is TrackState.LOST

    # Beacon returns in-gate: FRAMES_TO_REACQUIRE candidates -> REACQUIRE.
    states: list[TrackState] = []
    for _ in range(FRAMES_TO_REACQUIRE):
        states.append(sm.step(_det(0.8, CENTER), DT, k, k * DT, CENTER).state)
        k += 1
    assert states[0] is TrackState.LOST  # streak 1,2 still LOST
    assert states[FRAMES_TO_REACQUIRE - 1] is TrackState.REACQUIRE

    # FRAMES_TO_CONFIRM confirming frames -> back to TRACK.
    for _ in range(FRAMES_TO_CONFIRM - 1):
        r = sm.step(_det(0.8, CENTER), DT, k, k * DT, CENTER)
        k += 1
    r = sm.step(_det(0.8, CENTER), DT, k, k * DT, CENTER)
    assert r.state is TrackState.TRACK


def test_lost_timeout_returns_to_search():
    sm = _make()
    dets = [_det(0.9)] * (FRAMES_TO_ACQUIRE + FRAMES_TO_CONFIRM)
    _feed(sm, dets)
    k = len(dets)
    for _ in range(MAX_MISSES_BEFORE_LOST + 5):
        sm.step(None, DT, k, k * DT, CENTER)
        k += 1
    assert sm.state is TrackState.LOST

    # Exceed the LOST timeout with no candidate: fresh SEARCH, filter dropped.
    timed_out = False
    for _ in range(250):
        r = sm.step(None, DT, k, k * DT, CENTER)
        k += 1
        if r.state is TrackState.SEARCH:
            timed_out = True
            break
    assert timed_out
    assert sm._kf.active is False  # filter was reset -- no stale trajectory


def test_gate_rejects_far_candidates_in_track():
    sm = _make()
    dets = [_det(0.9)] * (FRAMES_TO_ACQUIRE + FRAMES_TO_CONFIRM)
    _feed(sm, dets)
    assert sm.state is TrackState.TRACK

    # A bright detection 500 px away is a different object: it must NOT feed
    # the filter and must count as a miss (but a single one won't drop lock).
    far = (CENTER[0] + 500.0, CENTER[1])
    r = sm.step(_det(0.9, far), DT, 100, 100 * DT, CENTER)
    assert r.state is TrackState.TRACK
    assert sm._track_misses == 1

    # A valid in-gate detection resets the miss counter.
    sm.step(_det(0.9, CENTER), DT, 101, 101 * DT, CENTER)
    assert sm._track_misses == 0


def test_acquire_aborts_back_to_search_on_miss_streak():
    sm = _make()
    dets = [_det(0.9)] * FRAMES_TO_ACQUIRE
    _feed(sm, dets)
    assert sm.state is TrackState.ACQUIRE

    for i in range(MISSES_TO_ABORT_ACQUIRE):
        r = sm.step(None, DT, 10 + i, (10 + i) * DT, CENTER)
    assert sm.state is TrackState.SEARCH
    assert sm._kf.active is False
    # And a fresh acquisition cycle can start over.
    results = _feed(sm, [_det(0.9)] * FRAMES_TO_ACQUIRE)
    assert sm.state is TrackState.ACQUIRE


def test_error_px_nan_rule_across_all_states():
    sm = _make()
    dets = [_det(0.9)] * (FRAMES_TO_ACQUIRE + FRAMES_TO_CONFIRM)
    dets += [None] * (MAX_MISSES_BEFORE_LOST)  # -> LOST
    dets += [_det(0.8, CENTER)] * (FRAMES_TO_REACQUIRE + FRAMES_TO_CONFIRM)  # -> TRACK
    results = _feed(sm, dets)

    assert any(r.state is TrackState.LOST for r in results)
    assert any(r.state is TrackState.REACQUIRE for r in results)
    for r in results:
        if r.state is TrackState.TRACK:
            assert not math.isnan(r.error_px[0]) and not math.isnan(r.error_px[1])
        else:
            assert math.isnan(r.error_px[0]) and math.isnan(r.error_px[1])
        assert 0.0 <= r.confidence <= 1.0


def test_track_result_emitted_every_frame_even_in_search():
    sm = _make()
    results = _feed(sm, [None] * 5)
    assert len(results) == 5
    for r in results:
        assert r.state is TrackState.SEARCH
        assert r.confidence == 0.0
        assert r.centroid_px == (0.0, 0.0)
        assert r.bbox_px == (0.0, 0.0, 0.0, 0.0)
        assert math.isnan(r.error_px[0])


def test_error_px_is_boresight_relative_in_track():
    # Contract pin: error_px = centroid - image_center, positive right/down.
    sm = _make()
    dets = [_det(0.9)] * (FRAMES_TO_ACQUIRE + FRAMES_TO_CONFIRM)
    r = _feed(sm, dets)[-1]
    assert r.state is TrackState.TRACK
    assert r.error_px == (0.0, 0.0)  # beacon at CENTER is dead center

    # Beacon 100 px right of boresight -> +x error, 0 y error.
    sm2 = _make()
    dets2 = [_det(0.9, (740.0, 360.0))] * (FRAMES_TO_ACQUIRE + FRAMES_TO_CONFIRM)
    r2 = _feed(sm2, dets2)[-1]
    assert r2.state is TrackState.TRACK
    assert abs(r2.error_px[0] - 100.0) <= 1.0
    assert abs(r2.error_px[1]) <= 1.0