"""tests/test_mock_telemetry.py -- Test suite for MockTelemetrySource."""

from __future__ import annotations

import math
import numpy as np
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from core.contracts import TelemetryPacket, TrackState
from ui.mock_telemetry import MockTelemetrySource


def get_qapp():
    """Ensure QApplication instance exists for Qt timer tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_mock_telemetry_schedule_sequence():
    """Verify that MockTelemetrySource transitions through all 5 states in exact order."""
    source = MockTelemetrySource(time_scale=10.0)

    observed_states = []
    expected_order = [
        TrackState.SEARCH,
        TrackState.ACQUIRE,
        TrackState.TRACK,
        TrackState.LOST,
        TrackState.REACQUIRE,
        TrackState.TRACK,
    ]

    # Step through cycles until all expected states are seen
    for _ in range(600):  # 20 simulated seconds
        packet, img = source.step()
        if not observed_states or observed_states[-1] != packet.track_state:
            observed_states.append(packet.track_state)
        if len(observed_states) == len(expected_order):
            break

    assert observed_states == expected_order, (
        f"Expected state sequence {expected_order}, got {observed_states}"
    )


def test_mock_telemetry_packet_fields_and_image():
    """Verify fields of TelemetryPacket and properties of rendered frame."""
    source = MockTelemetrySource(width_px=320, height_px=240, time_scale=1.0)

    packet, img = source.step()

    # Check packet types & ranges
    assert isinstance(packet, TelemetryPacket)
    assert packet.frame_id == 1
    assert packet.timestamp_s > 0.0
    assert 25.0 <= packet.fps <= 35.0
    assert isinstance(packet.track_state, TrackState)
    assert isinstance(packet.error_px, tuple) and len(packet.error_px) == 2
    assert 0.0 <= packet.lock_fraction <= 1.0
    assert packet.loop_time_s > 0.0

    # Check image shape & dtype
    assert isinstance(img, np.ndarray)
    assert img.shape == (240, 320, 3)
    assert img.dtype == np.uint8


def test_mock_telemetry_qt_timer():
    """Verify QTimer emission of telemetry_updated signal."""
    app = get_qapp()

    source = MockTelemetrySource(time_scale=100.0)  # Super fast timer
    emitted_packets = []

    def on_telemetry(pkt, img):
        emitted_packets.append(pkt)
        if len(emitted_packets) >= 5:
            source.stop()
            app.quit()

    source.telemetry_updated.connect(on_telemetry)
    source.start()

    # Process events for up to 1 second real time
    import time
    for _ in range(20):
        QCoreApplication.processEvents()
        time.sleep(0.01)

    source.stop()
    assert len(emitted_packets) > 0, "No telemetry signals emitted by QTimer"
