# ui/ — UI Shell & Mission-Control Dashboard

This module provides the dark mission-control UI shell, live telemetry dashboard, and optical video feed display for the FSOC Coarse-Alignment Tracking Simulator (SIH 26169).

## Module Structure

- `__init__.py`: Package initializer exporting palette color tokens.
- `palette.py`: Single source of truth for color constants (`BG_*`, `LINE_*`, `TEXT_*`, `COLOR_*`) and exhaustive `STATE_COLORS` dictionary.
- `style.qss`: Custom Qt stylesheet styling every widget (buttons, sliders, spinboxes, comboboxes, tooltips, panels) with zero default OS chrome.
- `mock_telemetry.py`: `MockTelemetrySource` emitting `TelemetryPacket` dataclasses and procedurally generated numpy BGR frames at 30 Hz across a 5-state cycle (`SEARCH` -> `ACQUIRE` -> `TRACK` -> `LOST` -> `REACQUIRE` -> `TRACK`).
- `overlay.py`: `VideoPane` widget rendering scaled video frames preserving aspect ratio with custom `QPainter` HUD overlay (center crosshair, bbox/centroid, dashed error vector, state accents, 4-corner telemetry HUD).
- `charts.py`: `RollingChart` for metric trends and `LockStateIndicator` for the mission-critical 230px state banner with 12% alpha fill, solid border, 34px bold text, and 1 Hz blinking on `LOST`.
- `analytics_window.py`: Non-modal full-session analytics page with summary metrics, state distribution, complete-run charts, a sortable/filterable frame log, archived-log loading, and JSON/CSV export.
- `main_window.py`: `MainWindow` cockpit layout (1440x900 minimum), `ConfigPanel`, `TelemetryStrip`, analytics navigation, automatic run-log persistence, and the `--selftest` CLI flag.

## Key Design Principles

1. **Strict Palette Consistency**: Every hex color used in `style.qss` is guaranteed by automated tests to exist in `palette.py`.
2. **Single Source of Truth**: `STATE_COLORS` exhaustively maps all 5 `TrackState` enum members (`SEARCH`, `ACQUIRE`, `TRACK`, `LOST`, `REACQUIRE`) with runtime assertions.
3. **No External Heavy Dependencies**: Uses PySide6 and pure NumPy for high-performance offscreen rendering and testing.

## Analytics and Performance Logs

Select `ANALYTICS / LOGS` in the cockpit header to open the analytics page without interrupting tracking. The page provides:

- Eight session KPIs: frame count, duration, average FPS, acquisition time, lock retention, and mean/RMSE/maximum tracking error.
- Full-session FPS, tracking-error, and lock-quality trends plus tracking-state distribution.
- A frame-by-frame table containing every `TelemetryPacket` field with explicit units and `N/A` for unavailable values.
- Exact tracking-state filters, typed column sorting, archived JSON-log selection, and manual JSON/CSV exports.

Stopping a started simulation automatically writes a strict JSON performance log under `Documents/FSOC Simulator/performance_logs`. Starting again resumes the same telemetry-source session and updates that run log; loading another video starts a new session. JSON contains the summary and complete packet records, while CSV provides one spreadsheet-ready row per packet.

## Running the UI

### Live Mission-Control Dashboard
```bash
python -m ui.main_window
```

### Offscreen Self-Test & Screenshot Generation
```bash
python -m ui.main_window --selftest
```
Generates state screenshots:
- `selftest_SEARCH.png`
- `selftest_ACQUIRE.png`
- `selftest_TRACK.png`
- `selftest_LOST.png`
- `selftest_REACQUIRE.png`

## Running Automated Tests

```bash
pytest tests -q
```
