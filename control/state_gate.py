"""control/state_gate.py -- gating logic for PID control activation based on TrackState.

The control loop MUST NOT apply PID corrections during SEARCH, ACQUIRE, or LOST.
PID corrections are only applied during TRACK and REACQUIRE states when lock is active/confirmed.
"""

from core.contracts import TrackState

__all__ = ["ACTIVE_STATES", "is_control_active"]

ACTIVE_STATES: set[TrackState] = {
    TrackState.TRACK,
    TrackState.REACQUIRE,
}


def is_control_active(state: TrackState) -> bool:
    """Return True if control commands should be generated for the given TrackState.

    - SEARCH, ACQUIRE, LOST: Return False (gated off; zero output; PID reset/held).
    - TRACK, REACQUIRE: Return True (gated on; PID update applied).
    """
    return state in ACTIVE_STATES
