"""tests/test_ui_smoke.py -- Offscreen QApplication smoke test (~6s accelerated run)."""

from __future__ import annotations

import os
import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from core.contracts import TrackState
from ui.main_window import MainWindow


def test_ui_offscreen_smoke_run():
    """Run MainWindow offscreen for accelerated ~6s simulation, observing all 5 states."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Create window with 10x accelerated telemetry source
    window = MainWindow(time_scale=10.0)
    window.resize(1440, 900)
    window.show()

    observed_states = set()
    source = window.telemetry_source

    # Step through simulation frames (approx 600 frames = 20s sim time at 10x speed)
    for _ in range(600):
        packet, img = source.step()
        window._on_telemetry_updated(packet, img)
        QCoreApplication.processEvents()

        observed_states.add(packet.track_state)
        if len(observed_states) == 5:
            break

    # Assert all 5 TrackState members were observed during the run
    expected_states = {
        TrackState.SEARCH,
        TrackState.ACQUIRE,
        TrackState.TRACK,
        TrackState.LOST,
        TrackState.REACQUIRE,
    }
    assert observed_states == expected_states, (
        f"Expected all 5 states {expected_states}, but observed {observed_states}"
    )

    window.close()
