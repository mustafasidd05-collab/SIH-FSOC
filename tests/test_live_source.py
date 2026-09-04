"""tests/test_live_source.py -- unit and integration tests for runtime LiveTelemetrySource."""

import math
import numpy as np
import pytest

from core.contracts import TelemetryPacket, TrackState
from runtime.live_source import LiveTelemetrySource


def test_live_telemetry_source_initialization():
    """Verify LiveTelemetrySource creation and initial contract shapes."""
    source = LiveTelemetrySource(width_px=640, height_px=480, time_scale=1.0)
    packet, img = source.step()

    assert isinstance(packet, TelemetryPacket)
    assert isinstance(img, np.ndarray)
    assert img.shape == (480, 640, 3)
    assert packet.frame_id == 1
    assert packet.fps == 30.0


@pytest.mark.parametrize("seed", [1, 7, 42, 123])
def test_live_telemetry_source_closed_loop_tracking(seed: int):
    """Verify live pipeline advances through SEARCH -> ACQUIRE -> TRACK and closes loop across various noise seeds."""
    source = LiveTelemetrySource(width_px=640, height_px=480, time_scale=1.0, seed=seed)

    states_seen = set()
    initial_track_error = None
    final_track_error = None

    # Step through 150 frames (5 seconds simulation @ 30 Hz)
    for _ in range(150):
        packet, img = source.step()
        states_seen.add(packet.track_state)

        if packet.track_state == TrackState.TRACK:
            err_mag = math.hypot(packet.error_px[0], packet.error_px[1])
            if initial_track_error is None:
                initial_track_error = err_mag
            final_track_error = err_mag

    # Must transition from SEARCH into TRACK
    assert TrackState.SEARCH in states_seen, "Never passed through SEARCH state"
    assert TrackState.TRACK in states_seen, "Pipeline failed to reach TRACK state!"

    # Verify closed-loop PID error reduction under TRACK
    assert initial_track_error is not None
    assert final_track_error is not None
    assert final_track_error < initial_track_error, (
        f"Closed-loop error failed to shrink under TRACK: {initial_track_error:.2f}px -> {final_track_error:.2f}px"
    )
    assert final_track_error < 25.0, f"Residual tracking error under TRACK too large: {final_track_error:.2f}px"

    print(f"\n[Live Source Closed Loop] Reached TRACK! Error reduced: {initial_track_error:.2f}px -> {final_track_error:.2f}px")
    print(f"Final Lock Fraction: {packet.lock_fraction * 100.0:.1f}% | Acquisition Time: {packet.acquisition_time_s:.2f}s")
