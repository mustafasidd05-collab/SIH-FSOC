# PROJECT STATUS -- FSOC Coarse-Alignment Tracking Simulator (SIH 26169)

> Every agent updates this file before ending a task. Keep it short and current -- this is
> the first thing a new agent (or Mustafa) reads to understand where things stand right
> now. Do not let it become a changelog; that's what `phase_history.md` is for.

**Last updated:** 2026-09-25 -- Primary Agent
**Current phase:** All deliverables complete & verified -- Standalone Executable (`dist/fsoc_sim/fsoc_sim.exe`), 133/133 tests passing, Complete PPT Presentation Diagrams suite (High-Res 2400×1350 JPG and vector SVGs in `ppt_assets/` and `ppt_diagrams.html` including unified Technical Approach slide with Technologies Used, Methodologies, and Closed-Loop Architecture Flowchart + 9 Mermaid deep-dive diagrams), `README.md`, `USER_MANUAL.md`, and `TECHNICAL_REPORT.md`.

## Module status

| Module | Status | Notes |
|---|---|---|
| `core/contracts.py` | Done -- verified | All 5 dataclasses + TrackState enum (5 states: SEARCH, ACQUIRE, TRACK, LOST, REACQUIRE), frozen; smoke-tested |
| `sim/` | Done -- verified | Scene, camera model, rendering pipeline with distractor role & appearance overrides; `SpiralMotionConfig` (Archimedean spiral, analytically evaluated); `Scene.beacon_configs` property |
| `disturbance/` | Done -- verified | Turbulence, vibration, sensor noise, camera motion blur, and cloud occlusion models |
| `tracking/` | Done -- verified | detect + kalman + state_machine + pipeline + `ai_filter.py` (lightweight CNN patch classifier) |
| `control/` | Done -- verified | `PID1D` with anti-windup & derivative filtering, `PanTiltPID`, `is_control_active` gating, `ControlLoop`; deliberate `DEFAULT_MAX_OUTPUT_STEP` slew-rate limiting |
| `ui/` | Done -- verified | MainWindow cockpit layout (scrollable sidebar, no clipping), QSS theme, VideoPane HUD overlay, LockStateIndicator, RollingChart, MockTelemetrySource & LiveTelemetrySource, `--video` CLI support; 60 FPS nominal rate, `SWITCH TO VIRTUAL SCENE` button, source status chip, live wiring of scene velocity/size/patterns, fault decoy toggle, disturbance presets/sliders, PID gain tuning + integral reset, header EXPORT LOG button |
| `runtime/` | Done -- verified | `LiveTelemetrySource` upgraded to nominal 60 FPS (dt=16.67ms, 180-frame lookback buffer); exposes full live-update API: `set_motion_pattern`, `set_target_speed`, `set_target_size`, `set_disturbance_levels`, `set_pid_gains`, `toggle_decoy`, `apply_disturbance_profile`; `_rebuild_scene` / `_rebuild_disturbance` helpers; `step()` passes dynamic `RenderConfig` + `beacon_configs` to `sim.render`. |
| `telemetry/` | Done -- verified | `PerformanceLogger` and `ExportSummary` for telemetry aggregation, metrics calculation, and JSON performance log export |
| `training/` | Done -- verified | Auto-dataset generator (`generate_dataset.py`) and CNN trainer (`train_classifier.py`) reusing sim/disturbance modules |
| `config/` | Done -- verified | YAML default configuration (`default_config.yaml`) upgraded to 60 FPS nominal rate, loader/manager (`config_manager.py`) |
| `build/` | Done -- verified | PyInstaller standalone executable specification (`build/build_executable.spec`); binary built in `dist/fsoc_sim/fsoc_sim.exe` and verified via `--selftest`. |

(Status values: Not started / In progress / Blocked / Done -- pending review / Done -- verified)

## What's working right now

- Standalone executable deliverable: `dist/fsoc_sim/fsoc_sim.exe` generated via PyInstaller and smoke-verified (`--selftest` passes in 1.08s wall time, capturing all 5 states).
- Project documentation deliverables: `USER_MANUAL.md` and `TECHNICAL_REPORT.md` fully authored and up to date.
- Python 3.12 venv at `venv/` with all runtime deps (OpenCV, NumPy, SciPy, filterpy, PySide6, PyInstaller) + pytest installed via pinned-free `requirements*.txt`.
- `core/contracts.py` defines every cross-module data shape (SimFrame, CameraState, TargetState, TrackResult, TelemetryPacket, TrackState) -- immutable, unit-documented, smoke-tested.
- `core/camera/input_adapter.py`: Benchmark-2 MP4 video input adapter enabling external video file processing.
- `evaluate_video.py`: Headless evaluator script for custom .mp4 videos with accurate acquisition time calculation, lock retention rate, RMSE, and JSON performance log export.
- `ui/main_window.py`: Supports `--video <path>` CLI flag to run live GUI tracking on custom MP4 video files.
- **60 FPS Simulation & Virtual Scene Switch:**
  - Simulation and UI loop fully upgraded to 60 FPS (16.67 ms nominal step interval, 180-frame rolling telemetry window).
  - Header source chip `lbl_source_chip` displays current active feed (`[ VIRTUAL SCENE (60 Hz) ]` vs `[ MP4: <filename> ]`).
  - `SWITCH TO VIRTUAL SCENE` (`btn_reset_scene`) button enables smooth 1-click transition from MP4 video evaluation back to the synthetic virtual scene while inheriting current sidebar parameters.
- Total passing tests: 133/133 (`pytest tests -q`).

## Self-verify results (UI, Executable & Integration)

- `pytest tests -q`: **133 passed in 158.45s** — 0 failures, 0 errors.
- `pytest tests/test_live_source.py -v`: **5 passed in 46.85s** (verifying closed-loop tracking across seeds 1, 7, 42, 123).
- `pytest tests/test_ui_controls.py -v`: **8 passed**.
- `pytest tests/test_ui_logic.py -k test_palette_qss_hex_divergence`: **1 passed** (zero QSS hex divergence from `palette.py`).
- `python -m ui.main_window --selftest`: All 5 states (SEARCH, ACQUIRE, TRACK, LOST, REACQUIRE) captured offscreen, 100.00% ticks within 2x nominal 60 Hz interval (16.67 ms), screenshots saved.
- `.\dist\fsoc_sim\fsoc_sim.exe --selftest`: **All 5 states captured offscreen, 100.00% ticks within 60 Hz interval (18.09 ms wall loop time), exit code 0.**

## What's blocked

- Graphiti / GitHub MCP -- explicitly deferred by Mustafa; keys to be handed over in a separate task.

## Next up

- Project complete. Ready for presentation and evaluation submission.
