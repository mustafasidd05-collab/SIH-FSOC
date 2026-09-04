# ui/ — UI Shell & Mission-Control Dashboard

This module provides the dark mission-control UI shell, live telemetry dashboard, and optical video feed display for the FSOC Coarse-Alignment Tracking Simulator (SIH 26169).

## Module Structure

- `__init__.py`: Package initializer exporting palette color tokens.
- `palette.py`: Single source of truth for color constants (`BG_*`, `LINE_*`, `TEXT_*`, `COLOR_*`) and exhaustive `STATE_COLORS` dictionary.
- `style.qss`: Custom Qt stylesheet styling every widget (buttons, sliders, spinboxes, comboboxes, tooltips, panels) with zero default OS chrome.
- `mock_telemetry.py`: `MockTelemetrySource` emitting `TelemetryPacket` dataclasses and procedurally generated numpy BGR frames at 30 Hz across a 5-state cycle (`SEARCH` -> `ACQUIRE` -> `TRACK` -> `LOST` -> `REACQUIRE` -> `TRACK`).
- `overlay.py`: `VideoPane` widget rendering scaled video frames preserving aspect ratio with custom `QPainter` HUD overlay (center crosshair, bbox/centroid, dashed error vector, state accents, 4-corner telemetry HUD).
- `charts.py`: `RollingChart` for metric trends and `LockStateIndicator` for the mission-critical 230px state banner with 12% alpha fill, solid border, 34px bold text, and 1 Hz blinking on `LOST`.
- `main_window.py`: `MainWindow` cockpit layout (1440x900 minimum), `ConfigPanel`, `TelemetryStrip`, and `--selftest` CLI flag.

## Key Design Principles

1. **Strict Palette Consistency**: Every hex color used in `style.qss` is guaranteed by automated tests to exist in `palette.py`.
2. **Single Source of Truth**: `STATE_COLORS` exhaustively maps all 5 `TrackState` enum members (`SEARCH`, `ACQUIRE`, `TRACK`, `LOST`, `REACQUIRE`) with runtime assertions.
3. **No External Heavy Dependencies**: Uses PySide6 and pure NumPy for high-performance offscreen rendering and testing.

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
