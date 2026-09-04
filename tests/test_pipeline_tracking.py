"""Integration tests for tracking/pipeline.py over the synthetic clips.

What these prove (the self-verify contract from the module plan):
  * acquisition happens in a bounded number of frames per clip,
  * tracking error (filtered centroid vs ground truth) stays in a sane band,
  * the dropout clip goes LOST and REACQUIREs -- it never silently remains
    in TRACK with stale data.
"""

import math

import numpy as np

from core.contracts import CameraState, SimFrame, TrackState
from tests.fixtures.generate_clips import load_clip
from tracking.pipeline import TrackPipeline
from tracking.state_machine import MAX_MISSES_BEFORE_LOST

MAX_ACQUISITION_FRAMES_CLEAN = 10
MAX_ACQUISITION_FRAMES_NOISY = 12
REACQUIRE_MUST_APPEAR_WITHIN = 12  # frames after the dropout window ends
RE_LOCKED_WITHIN = 12  # frames after the dropout window ends
MAX_CLEAN_MAE_PX = 1.5
MAX_CLEAN_RMSE_PX = 2.0
MAX_NOISY_RMSE_PX = 4.0


def _run_clip(name: str) -> tuple[TrackPipeline, list]:
    clip = load_clip(name)
    width, height = int(clip["width"]), int(clip["height"])
    fps = float(clip["fps"])
    camera = CameraState(
        pan_rad=0.0,
        tilt_rad=0.0,
        pan_min_rad=-1.5,
        pan_max_rad=1.5,
        tilt_min_rad=-0.5,
        tilt_max_rad=0.5,
        fov_h_rad=0.7,
        fov_v_rad=0.5,
        width_px=width,
        height_px=height,
    )

    frames = [
        SimFrame(
            frame_id=i,
            timestamp_s=i / fps,
            image=clip["images"][i],
            camera=camera,
        )
        for i in range(clip["images"].shape[0])
    ]

    pipeline = TrackPipeline()
    results = [pipeline.process(f) for f in frames]
    return pipeline, results


def _assert_basic_contract(results):
    """TrackResult every frame; NaN rule; confidence bounds."""
    for r in results:
        assert 0.0 <= r.confidence <= 1.0
        if r.state is TrackState.TRACK:
            assert not math.isnan(r.error_px[0]) and not math.isnan(r.error_px[1])
        else:
            assert math.isnan(r.error_px[0]) and math.isnan(r.error_px[1])


def _track_errors(results, gt_xy: np.ndarray, gt_visible: np.ndarray) -> np.ndarray:
    """Filtered-centroid error vs ground truth on visible TRACK frames."""
    errors = []
    for r, vis, (gx, gy) in zip(results, gt_visible, gt_xy):
        if vis and r.state is TrackState.TRACK:
            errors.append(math.hypot(r.centroid_px[0] - gx, r.centroid_px[1] - gy))
    return np.asarray(errors, dtype=float)


def test_clean_clip_acquires_and_tracks_accurately():
    clip = load_clip("clip_clean")
    _, results = _run_clip("clip_clean")
    states = [r.state for r in results]
    _assert_basic_contract(results)

    first_track = states.index(TrackState.TRACK)
    assert first_track <= MAX_ACQUISITION_FRAMES_CLEAN, f"acquisition slow: frame {first_track}"
    assert float(results[first_track].timestamp_s) < 0.25  # < 250 ms to lock

    errors = _track_errors(results, clip["gt_xy"], clip["gt_visible"])
    assert len(errors) > 100  # locked for most of the clip
    assert float(np.mean(errors)) < MAX_CLEAN_MAE_PX
    assert float(np.sqrt(np.mean(errors**2))) < MAX_CLEAN_RMSE_PX
    # Lock fraction must be high: nearly the whole clip in TRACK.
    assert states.count(TrackState.TRACK) / len(states) > 0.9


def test_noisy_clip_still_acquires_and_tracks():
    clip = load_clip("clip_noisy")
    _, results = _run_clip("clip_noisy")
    states = [r.state for r in results]
    _assert_basic_contract(results)

    first_track = states.index(TrackState.TRACK)
    assert first_track <= MAX_ACQUISITION_FRAMES_NOISY, f"acquisition slow: frame {first_track}"

    errors = _track_errors(results, clip["gt_xy"], clip["gt_visible"])
    assert len(errors) > 100
    assert float(np.sqrt(np.mean(errors**2))) < MAX_NOISY_RMSE_PX

    # Raw measurement noise is sigma=10; the smooth estimate must be far
    # tighter than that or the filter is doing nothing.
    assert float(np.sqrt(np.mean(errors**2))) < 4.0
    assert states.count(TrackState.TRACK) / len(states) > 0.9


def test_dropout_clip_goes_lost_then_reacquires():
    clip = load_clip("clip_dropout")
    _, results = _run_clip("clip_dropout")
    states = [r.state for r in results]
    _assert_basic_contract(results)

    dropout_start, dropout_end = int(clip["dropout_start"]), int(clip["dropout_end"])

    # 1. Locked BEFORE the dropout (this is a real lock-loss, not a no-lock).
    assert all(s is TrackState.TRACK for s in states[dropout_start - 15 : dropout_start - 3])

    # 2. The state machine tolerates up to MAX_MISSES_BEFORE_LOST (10) frames
    #    of silence in TRACK before dropping to LOST.  After that threshold
    #    fires, no silent TRACK is permitted until REACQUIRE re-locks.
    first_lost = next(i for i, s in enumerate(states) if s is TrackState.LOST)
    assert first_lost <= dropout_start + MAX_MISSES_BEFORE_LOST + 1, (
        f"LOST never fired (first LOST at frame {first_lost})"
    )
    reacquire_idx = states.index(TrackState.REACQUIRE)
    assert all(
        s is not TrackState.TRACK for s in states[first_lost:reacquire_idx]
    ), "silent TRACK between LOST and REACQUIRE"

    # 3. REACQUIRE fires shortly after the beacon returns...
    assert dropout_end < reacquire_idx <= dropout_end + REACQUIRE_MUST_APPEAR_WITHIN

    # 4. ...and TRACK resumes shortly after REACQUIRE.
    first_track_after = next(
        i for i in range(reacquire_idx, len(states)) if states[i] is TrackState.TRACK
    )
    assert first_track_after - dropout_end <= RE_LOCKED_WITHIN