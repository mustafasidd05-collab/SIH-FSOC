"""evaluate_video.py -- Headless Benchmark-2 video evaluation script.

Runs fully autonomous detection, tracking, and evaluation on an external .mp4
video file, computes required graded metrics (acquisition time, FPS, RMSE tracking
error, lock retention rate), and exports a performance log.

Usage:
    python evaluate_video.py path/to/video.mp4 [output_log.json]
"""

from __future__ import annotations

import sys
import math
from pathlib import Path

from core.camera.input_adapter import VideoInputAdapter
from tracking.pipeline import TrackPipeline
from telemetry.performance_logger import PerformanceLogger
from core.contracts import TelemetryPacket, TrackState


def evaluate_video(video_path: str | Path, output_json: str | Path = "performance_log.json") -> int:
    path = Path(video_path)
    if not path.exists():
        print(f"Error: Video file not found: {path}", file=sys.stderr)
        return 1

    pipeline = TrackPipeline()
    logger = PerformanceLogger()

    print(f"==================================================")
    print(f"FSOC Benchmark-2 Headless Video Evaluator")
    print(f"Input Video: {path.resolve()}")
    print(f"==================================================")

    acquisition_time_s = float("nan")
    search_start_time_s: float | None = 0.0
    recent_states = []
    max_lookback = 90

    with VideoInputAdapter(path) as adapter:
        frame_id = 0
        fps = adapter.fps_val

        while frame := adapter.read_frame():
            t_s = frame.timestamp_s
            result = pipeline.process(frame)

            # Track acquisition time (time from SEARCH to first TRACK)
            if result.state == TrackState.SEARCH and search_start_time_s is None:
                search_start_time_s = t_s
            elif result.state == TrackState.TRACK and math.isnan(acquisition_time_s):
                if search_start_time_s is not None:
                    acquisition_time_s = t_s - search_start_time_s
                else:
                    acquisition_time_s = t_s

            recent_states.append(result.state)
            if len(recent_states) > max_lookback:
                recent_states.pop(0)

            track_count = sum(1 for s in recent_states if s in (TrackState.TRACK, TrackState.REACQUIRE))
            lock_fraction = track_count / len(recent_states) if recent_states else 0.0

            # Note on external-video mode: error_az_rad and error_el_rad are zeroed
            # because an arbitrary judge-supplied mp4 has no real PTZ or calibrated
            # focal length mapping; pixel error is the honest evaluation metric here.
            packet = TelemetryPacket(
                frame_id=frame_id,
                timestamp_s=t_s,
                fps=fps,
                track_state=result.state,
                error_px=result.error_px,
                error_az_rad=0.0,
                error_el_rad=0.0,
                lock_fraction=lock_fraction,
                acquisition_time_s=acquisition_time_s,
                loop_time_s=0.0,
            )
            logger.record(packet)

            state_str = result.state.value
            err_str = f"({result.error_px[0]:+.1f}, {result.error_px[1]:+.1f}) px" if not math.isnan(result.error_px[0]) else "(N/A)"
            print(f"Frame #{frame_id:04d} | Time: {t_s:6.2f}s | State: {state_str:10s} | Error: {err_str}", end="\r")

            frame_id += 1

    summary = logger.compute_summary()
    logger.export_json(output_json)

    print("\n\n==================================================")
    print("EVALUATION RESULTS SUMMARY")
    print("==================================================")
    print(f"Total Frames Processed : {summary.total_frames}")
    print(f"Video Duration         : {summary.duration_s:.2f} s")
    print(f"Average Processing FPS : {summary.average_fps:.2f} FPS")
    print(f"Acquisition Time       : {summary.acquisition_time_s:.3f} s" if not math.isnan(summary.acquisition_time_s) else "Acquisition Time       : N/A")
    print(f"Lock Retention Rate    : {summary.lock_retention_rate * 100.0:.2f}%")
    print(f"Mean Tracking Error    : {summary.mean_error_px:.2f} px")
    print(f"RMSE Tracking Error    : {summary.rmse_error_px:.2f} px")
    print(f"Max Tracking Error     : {summary.max_error_px:.2f} px")
    print(f"Performance Log Export : {Path(output_json).resolve()}")
    print("==================================================")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evaluate_video.py <path_to_video.mp4> [output_log.json]")
        sys.exit(1)
    
    vid = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "performance_log.json"
    sys.exit(evaluate_video(vid, out))
