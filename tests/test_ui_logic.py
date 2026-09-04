"""tests/test_ui_logic.py -- Tests for UI logic, palette/QSS hex alignment, charts, and mapping asserts."""

from __future__ import annotations

import re
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from core.contracts import TrackState
from ui.charts import LockStateIndicator, RollingChart
from ui.palette import ALL_HEX_COLORS, STATE_COLORS


def get_qapp():
    """Ensure QApplication instance exists for Qt widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_palette_qss_hex_divergence():
    """Verify that every hex color in style.qss is defined in palette.py."""
    qss_path = Path(__file__).parent.parent / "ui" / "style.qss"
    assert qss_path.exists(), f"style.qss not found at {qss_path}"

    qss_content = qss_path.read_text(encoding="utf-8")
    hex_matches = re.findall(r"#[0-9A-Fa-f]{6}\b", qss_content)
    qss_colors = {h.upper() for h in hex_matches}

    assert qss_colors, "No hex color codes found in style.qss"
    
    divergent_colors = qss_colors - ALL_HEX_COLORS
    assert not divergent_colors, (
        f"The following hex colors in style.qss are not in palette.py: {divergent_colors}"
    )


def test_exhaustive_state_color_mapping():
    """Verify that STATE_COLORS exhaustively maps all TrackState enum members."""
    assert set(STATE_COLORS.keys()) == set(TrackState), (
        f"STATE_COLORS keys {set(STATE_COLORS.keys())} do not match set(TrackState) {set(TrackState)}"
    )
    assert len(STATE_COLORS) == len(TrackState) == 5


def test_lock_state_indicator_imports_state_colors():
    """Verify LockStateIndicator uses STATE_COLORS from palette.py directly."""
    app = get_qapp()
    indicator = LockStateIndicator()
    
    for state in TrackState:
        indicator.set_state(state)
        assert indicator._state == state
        assert STATE_COLORS[state] is not None


def test_rolling_chart_buffer_logic():
    """Verify RollingChart capacity and push/clear logic."""
    app = get_qapp()
    chart = RollingChart(title="FPS Test", capacity=10)

    assert len(chart._buffer) == 0

    for i in range(15):
        chart.push(float(i), 30.0 + i)

    # Max capacity is 10
    assert len(chart._buffer) == 10
    assert chart._buffer[0] == (5.0, 35.0)
    assert chart._buffer[-1] == (14.0, 44.0)

    chart.clear()
    assert len(chart._buffer) == 0
