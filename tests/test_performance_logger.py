"""Unit tests for telemetry/performance_logger.py."""

import csv
import json
import math
from pathlib import Path

import pytest

from core.contracts import TelemetryPacket, TrackState
from telemetry.performance_logger import ExportSummary, PerformanceLogger


def test_performance_logger_summary():
    logger = PerformanceLogger()

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
    assert summary.rmse_error_px == pytest.approx(math.hypot(1.5, -2.0))
    assert summary.max_error_px == pytest.approx(math.hypot(1.5, -2.0))
    assert summary.acquisition_time_s == pytest.approx(2.0 / 30.0)


def test_export_json_includes_every_packet_field(tmp_path):
    logger = PerformanceLogger()
    logger.record(
        TelemetryPacket(
            frame_id=17,
            timestamp_s=1.25,
            fps=59.5,
            track_state=TrackState.REACQUIRE,
            error_px=(2.5, -3.75),
            error_az_rad=0.002,
            error_el_rad=-0.003,
            lock_fraction=0.625,
            acquisition_time_s=0.45,
            loop_time_s=0.004,
        )
    )

    out_file = tmp_path / "nested" / "perf_log.json"
    logger.export_json(out_file)
    data = json.loads(out_file.read_text(encoding="utf-8"))

    assert set(data) == {"summary", "packets"}
    assert data["packets"] == [
        {
            "frame_id": 17,
            "timestamp_s": 1.25,
            "fps": 59.5,
            "track_state": "REACQUIRE",
            "error_px": [2.5, -3.75],
            "error_az_rad": 0.002,
            "error_el_rad": -0.003,
            "lock_fraction": 0.625,
            "acquisition_time_s": 0.45,
            "loop_time_s": 0.004,
        }
    ]


def test_export_json_converts_non_finite_values_to_null(tmp_path):
    logger = PerformanceLogger()
    logger.record(
        TelemetryPacket(
            frame_id=3,
            timestamp_s=float("inf"),
            fps=float("nan"),
            track_state=TrackState.TRACK,
            error_px=(float("nan"), float("-inf")),
            error_az_rad=float("inf"),
            error_el_rad=float("-inf"),
            lock_fraction=float("nan"),
            acquisition_time_s=float("nan"),
            loop_time_s=float("inf"),
        )
    )

    out_file = tmp_path / "non_finite.json"
    logger.export_json(out_file)
    data = json.loads(
        out_file.read_text(encoding="utf-8"),
        parse_constant=lambda value: pytest.fail(f"non-standard JSON value: {value}"),
    )

    assert data["packets"] == [
        {
            "frame_id": 3,
            "timestamp_s": None,
            "fps": None,
            "track_state": "TRACK",
            "error_px": [None, None],
            "error_az_rad": None,
            "error_el_rad": None,
            "lock_fraction": None,
            "acquisition_time_s": None,
            "loop_time_s": None,
        }
    ]
    assert data["summary"]["duration_s"] is None
    assert data["summary"]["average_fps"] is None
    assert data["summary"]["acquisition_time_s"] is None


def test_export_csv_has_all_columns_and_blank_non_finite_cells(tmp_path):
    logger = PerformanceLogger()
    logger.record(
        TelemetryPacket(
            frame_id=17,
            timestamp_s=1.25,
            fps=59.5,
            track_state=TrackState.REACQUIRE,
            error_px=(2.5, -3.75),
            error_az_rad=0.002,
            error_el_rad=-0.003,
            lock_fraction=0.625,
            acquisition_time_s=0.45,
            loop_time_s=0.004,
        )
    )
    logger.record(
        TelemetryPacket(
            frame_id=18,
            timestamp_s=float("nan"),
            fps=float("inf"),
            track_state=TrackState.LOST,
            error_px=(float("-inf"), float("nan")),
            error_az_rad=float("nan"),
            error_el_rad=float("inf"),
            lock_fraction=float("-inf"),
            acquisition_time_s=float("nan"),
            loop_time_s=float("inf"),
        )
    )

    out_file = tmp_path / "nested" / "perf_log.csv"
    logger.export_csv(out_file)
    with open(out_file, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    expected_fieldnames = [
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
    ]
    assert fieldnames == expected_fieldnames
    assert rows == [
        {
            "frame_id": "17",
            "timestamp_s": "1.25",
            "fps": "59.5",
            "track_state": "REACQUIRE",
            "error_x_px": "2.5",
            "error_y_px": "-3.75",
            "error_az_rad": "0.002",
            "error_el_rad": "-0.003",
            "lock_fraction": "0.625",
            "acquisition_time_s": "0.45",
            "loop_time_s": "0.004",
        },
        {
            "frame_id": "18",
            "timestamp_s": "",
            "fps": "",
            "track_state": "LOST",
            "error_x_px": "",
            "error_y_px": "",
            "error_az_rad": "",
            "error_el_rad": "",
            "lock_fraction": "",
            "acquisition_time_s": "",
            "loop_time_s": "",
        },
    ]
