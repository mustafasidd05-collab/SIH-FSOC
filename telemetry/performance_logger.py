"""telemetry/performance_logger.py -- telemetry aggregation & performance-log export.

Collects telemetry packets during a simulator run or video evaluation, computes
summary metrics (acquisition time, average tracking error / RMSE, lock rate, FPS),
and exports performance logs to JSON or CSV format.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

from core.contracts import TelemetryPacket, TrackState


@dataclass
class ExportSummary:
    """Summary metrics of a tracking session."""
    total_frames: int
    duration_s: float
    average_fps: float
    acquisition_time_s: float
    lock_retention_rate: float
    mean_error_px: float
    rmse_error_px: float
    max_error_px: float


class PerformanceLogger:
    """Aggregates telemetry packets and exports run performance summaries."""

    def __init__(self) -> None:
        self.packets: List[TelemetryPacket] = []

    def record(self, packet: TelemetryPacket) -> None:
        """Append a telemetry packet to the log."""
        self.packets.append(packet)

    def reset(self) -> None:
        """Clear recorded packets."""
        self.packets.clear()

    def compute_summary(self) -> ExportSummary:
        """Compute aggregated performance metrics across all recorded packets."""
        if not self.packets:
            return ExportSummary(
                total_frames=0,
                duration_s=0.0,
                average_fps=0.0,
                acquisition_time_s=float("nan"),
                lock_retention_rate=0.0,
                mean_error_px=0.0,
                rmse_error_px=0.0,
                max_error_px=0.0,
            )

        total_frames = len(self.packets)
        duration_s = self.packets[-1].timestamp_s - self.packets[0].timestamp_s
        if duration_s <= 0:
            duration_s = total_frames / 30.0

        fps_vals = [p.fps for p in self.packets]
        average_fps = float(sum(fps_vals) / len(fps_vals))

        # Acquisition time (first time acquisition completed)
        acq_times = [p.acquisition_time_s for p in self.packets if not math.isnan(p.acquisition_time_s)]
        acquisition_time_s = acq_times[0] if acq_times else float("nan")

        # Lock retention rate (fraction of frames in TRACK or REACQUIRE)
        track_states = sum(1 for p in self.packets if p.track_state in (TrackState.TRACK, TrackState.REACQUIRE))
        lock_retention_rate = track_states / total_frames

        # Tracking errors (in TRACK state)
        errors = []
        for p in self.packets:
            if p.track_state is TrackState.TRACK:
                ex, ey = p.error_px
                if not math.isnan(ex) and not math.isnan(ey):
                    errors.append(math.hypot(ex, ey))

        if errors:
            mean_error_px = float(sum(errors) / len(errors))
            rmse_error_px = float(math.sqrt(sum(e**2 for e in errors) / len(errors)))
            max_error_px = float(max(errors))
        else:
            mean_error_px = 0.0
            rmse_error_px = 0.0
            max_error_px = 0.0

        return ExportSummary(
            total_frames=total_frames,
            duration_s=duration_s,
            average_fps=average_fps,
            acquisition_time_s=acquisition_time_s,
            lock_retention_rate=lock_retention_rate,
            mean_error_px=mean_error_px,
            rmse_error_px=rmse_error_px,
            max_error_px=max_error_px,
        )

    def export_json(self, filepath: str | Path) -> None:
        """Export session summary and packet logs to a JSON file."""
        summary = self.compute_summary()
        data = {
            "summary": asdict(summary),
            "packets": [
                {
                    "frame_id": p.frame_id,
                    "timestamp_s": p.timestamp_s,
                    "fps": p.fps,
                    "track_state": p.track_state.value,
                    "error_px": p.error_px,
                    "lock_fraction": p.lock_fraction,
                    "acquisition_time_s": p.acquisition_time_s,
                }
                for p in self.packets
            ],
        }
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
