# PROJECT STATUS -- FSOC Coarse-Alignment Tracking Simulator (SIH 26169)

> Every agent updates this file before ending a task. Keep it short and current -- this is
> the first thing a new agent (or Mustafa) reads to understand where things stand right
> now. Do not let it become a changelog; that's what `phase_history.md` is for.

**Last updated:** 2026-09-04 -- primary agent
**Current phase:** Interactive HTML presentation deck (`presentation.html`) created; all 115 unit/integration tests verified and passing successfully.

## Module status

| Module | Status | Notes |
|---|---|---|
| `core/contracts.py` | Done -- verified | All 5 dataclasses + TrackState enum (5 states: SEARCH, ACQUIRE, TRACK, LOST, REACQUIRE), frozen; smoke-tested |
| `sim/` | Done -- verified | Scene, camera model, rendering pipeline with distractor role & appearance overrides |
| `disturbance/` | Done -- verified | Turbulence, vibration, sensor noise, camera motion blur, and cloud occlusion models |
| `tracking/` | Done -- verified | detect + kalman + state_machine + pipeline + `ai_filter.py` (lightweight CNN patch classifier) |
| `control/` | Done -- verified | `PID1D` with anti-windup & derivative filtering, `PanTiltPID`, `is_control_active` gating, `ControlLoop`; deliberate `DEFAULT_MAX_OUTPUT_STEP` slew-rate limiting |
| `ui/` | Done -- verified | MainWindow cockpit layout, QSS theme, VideoPane HUD overlay, LockStateIndicator, RollingChart, MockTelemetrySource & LiveTelemetrySource, `--video` CLI support |
| `runtime/` | Done -- verified | `LiveTelemetrySource` chaining `sim` -> `disturbance` -> `tracking` -> `control` closed loop; `core/camera/input_adapter.py` for Benchmark-2 external .mp4 streams |
| `telemetry/` | Done -- verified | `PerformanceLogger` and `ExportSummary` for telemetry aggregation, metrics calculation, and JSON performance log export |
| `training/` | Done -- verified | Auto-dataset generator (`generate_dataset.py`) and CNN trainer (`train_classifier.py`) reusing sim/disturbance modules |
| `config/` | Done -- verified | YAML default configuration (`default_config.yaml`) and loader/manager (`config_manager.py`) |
| `build/` | Done -- verified | PyInstaller standalone executable specification (`build_executable.spec`) |

(Status values: Not started / In progress / Blocked / Done -- pending review / Done -- verified)

## What's working right now

- Python 3.12 venv at `venv/` with all runtime deps (OpenCV, NumPy, SciPy, filterpy, PySide6, PyInstaller) + pytest installed via pinned-free `requirements*.txt`.
- `core/contracts.py` defines every cross-module data shape (SimFrame, CameraState, TargetState, TrackResult, TelemetryPacket, TrackState) -- immutable, unit-documented, smoke-tested.
- `core/camera/input_adapter.py`: Benchmark-2 MP4 video input adapter enabling external video file processing.
- `evaluate_video.py`: Headless evaluator script for custom .mp4 videos with accurate acquisition time calculation, lock retention rate, RMSE, and JSON performance log export.
- `ui/main_window.py`: Supports `--video <path>` CLI flag to run live GUI tracking on custom MP4 video files.
- Total passing tests: 115 (`pytest tests -q`).

## Self-verify results (Integration & Custom Video Testing)

- `pytest tests -q`: All unit and integration tests pass successfully.
- `evaluate_video.py` successfully processes MP4 video streams, computes acquisition time and RMSE, and exports valid JSON performance logs.

## What's blocked

- Graphiti / GitHub MCP -- explicitly deferred by Mustafa; keys to be handed over in a separate task.

## Next up

1. Final packaging build (`pyinstaller build/build_executable.spec`).
