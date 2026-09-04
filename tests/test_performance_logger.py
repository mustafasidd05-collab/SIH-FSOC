"""Unit tests for telemetry/performance_logger.py."""

import math
import pytest
from pathlib import Path

from core.contracts import TelemetryPacket, TrackState
from telemetry.performance_logger import PerformanceLogger, ExportSummary


def test_performance_logger_summary_and_export(tmp_path):
    logger = PerformanceLogger()

    # Add packets
    for i in range(10):
        packet = TelemetryPacket(
            frame_id=i,
            timestamp_s=i * (1.0 / 30.0),
            fps=30.0,
            track_state=TrackState.TRACK if i >= 2 else TrackState.SEARCH,
            error_px=(1.5, -2.0) if i >= 2 else (float("nan"), float("nan")),
            error_az_rad=0.01,
            error_el_rad=-0.01,
            lock_fraction=0.8,
            acquisition_time_s=2.0 / 30.0 if i == 2 else float("nan"),
            loop_time_s=0.01,
        )
        logger.record(packet)

    summary = logger.compute_summary()
    assert isinstance(summary, ExportSummary)
    assert summary.total_frames == 10
    assert summary.average_fps == 30.0
    assert summary.lock_retention_rate == 0.8  # 8 out of 10 in TRACK
    assert summary.mean_error_px == pytest.approx(math.hypot(1.5, -2.0))

    # Test JSON export
    out_file = tmp_path / "perf_log.json"
    logger.export_json(out_file)
    assert out_file.exists()
    assert out_file.stat().st_size > 0
