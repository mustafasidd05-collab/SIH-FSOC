"""telemetry/performance_logger.py -- telemetry aggregation & performance-log export.

Collects telemetry packets during a simulator run or video evaluation, computes
summary metrics (acquisition time, average tracking error / RMSE, lock rate, FPS),
and exports performance logs to JSON or CSV format.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

from core.contracts import TelemetryPacket, TrackState


_CSV_FIELDNAMES = (
    "frame_id",
    "timestamp_s",
    "fps",
    "track_state",
    "error_x_px",
    "error_y_px",
    "error_az_rad",
    "error_el_rad",
    "lock_fraction",
    "acquisition_time_s",
    "loop_time_s",
)


def _finite_or_none(value: int | float) -> int | float | None:
    """Return None for values that JSON and spreadsheets cannot represent cleanly."""
    return value if math.isfinite(value) else None


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
        self._reset_aggregates()

    def record(self, packet: TelemetryPacket) -> None:
        """Append a telemetry packet to the log."""
        self.packets.append(packet)
        if self._first_timestamp_s is None:
            self._first_timestamp_s = packet.timestamp_s
        self._last_timestamp_s = packet.timestamp_s
        self._fps_sum += packet.fps
        if (
            math.isnan(self._acquisition_time_s)
            and not math.isnan(packet.acquisition_time_s)
        ):
            self._acquisition_time_s = packet.acquisition_time_s
        if packet.track_state in (TrackState.TRACK, TrackState.REACQUIRE):
            self._locked_frame_count += 1
        if packet.track_state is TrackState.TRACK:
            error_x, error_y = packet.error_px
            if not math.isnan(error_x) and not math.isnan(error_y):
                error = math.hypot(error_x, error_y)
                self._tracking_error_count += 1
                self._tracking_error_sum += error
                self._tracking_error_squared_sum += error**2
                self._tracking_error_max = max(self._tracking_error_max, error)

    def reset(self) -> None:
        """Clear recorded packets."""
        self.packets.clear()
        self._reset_aggregates()

    def _reset_aggregates(self) -> None:
        self._first_timestamp_s: float | None = None
        self._last_timestamp_s: float | None = None
        self._fps_sum = 0.0
        self._acquisition_time_s = float("nan")
        self._locked_frame_count = 0
        self._tracking_error_count = 0
        self._tracking_error_sum = 0.0
        self._tracking_error_squared_sum = 0.0
        self._tracking_error_max = 0.0

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
        assert self._first_timestamp_s is not None
        assert self._last_timestamp_s is not None
        duration_s = self._last_timestamp_s - self._first_timestamp_s
        if duration_s <= 0:
            duration_s = total_frames / 30.0

        average_fps = float(self._fps_sum / total_frames)
        lock_retention_rate = self._locked_frame_count / total_frames

        if self._tracking_error_count:
            mean_error_px = float(
                self._tracking_error_sum / self._tracking_error_count
            )
            rmse_error_px = float(
                math.sqrt(
                    self._tracking_error_squared_sum / self._tracking_error_count
                )
            )
            max_error_px = float(self._tracking_error_max)
        else:
            mean_error_px = 0.0
            rmse_error_px = 0.0
            max_error_px = 0.0

        return ExportSummary(
            total_frames=total_frames,
            duration_s=duration_s,
            average_fps=average_fps,
            acquisition_time_s=self._acquisition_time_s,
            lock_retention_rate=lock_retention_rate,
            mean_error_px=mean_error_px,
            rmse_error_px=rmse_error_px,
            max_error_px=max_error_px,
        )

    def export_json(self, filepath: str | Path) -> None:
        """Export session summary and packet logs to a JSON file."""
        summary = self.compute_summary()
        data = {
            "summary": {
                name: _finite_or_none(value)
                for name, value in asdict(summary).items()
            },
            "packets": [
                {
                    "frame_id": p.frame_id,
                    "timestamp_s": _finite_or_none(p.timestamp_s),
                    "fps": _finite_or_none(p.fps),
                    "track_state": p.track_state.value,
                    "error_px": [
                        _finite_or_none(p.error_px[0]),
                        _finite_or_none(p.error_px[1]),
                    ],
                    "error_az_rad": _finite_or_none(p.error_az_rad),
                    "error_el_rad": _finite_or_none(p.error_el_rad),
                    "lock_fraction": _finite_or_none(p.lock_fraction),
                    "acquisition_time_s": _finite_or_none(p.acquisition_time_s),
                    "loop_time_s": _finite_or_none(p.loop_time_s),
                }
                for p in self.packets
            ],
        }
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, allow_nan=False)

    def export_csv(self, filepath: str | Path) -> None:
        """Export one spreadsheet-ready row per telemetry packet."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES)
            writer.writeheader()
            for packet in self.packets:
                writer.writerow(
                    {
                        "frame_id": packet.frame_id,
                        "timestamp_s": _finite_or_none(packet.timestamp_s),
                        "fps": _finite_or_none(packet.fps),
                        "track_state": packet.track_state.value,
                        "error_x_px": _finite_or_none(packet.error_px[0]),
                        "error_y_px": _finite_or_none(packet.error_px[1]),
                        "error_az_rad": _finite_or_none(packet.error_az_rad),
                        "error_el_rad": _finite_or_none(packet.error_el_rad),
                        "lock_fraction": _finite_or_none(packet.lock_fraction),
                        "acquisition_time_s": _finite_or_none(packet.acquisition_time_s),
                        "loop_time_s": _finite_or_none(packet.loop_time_s),
                    }
                )
