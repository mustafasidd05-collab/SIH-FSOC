"""ui/palette.py -- Single source of truth for UI color constants."""

from __future__ import annotations

from typing import Dict
from core.contracts import TrackState

# Neutrals
BG_ROOT = "#0A0D0F"
BG_PANEL = "#11161A"
BG_INSET = "#0C1013"
BG_RAISED = "#1A2126"

LINE = "#232C33"
LINE_STRONG = "#2E3A42"

TEXT_0 = "#D9E0E4"
TEXT_1 = "#93A0A8"
TEXT_2 = "#5B6770"
OFF = "#39434A"

# Signal family (ONLY chroma in the whole app, used ONLY for lock-state)
COLOR_TRACK = "#00E676"      # Green
COLOR_ACQUIRE = "#39C5CF"    # Cyan
COLOR_SEARCH = "#FFB300"     # Amber
COLOR_LOST = "#FF4D4F"       # Red
COLOR_REACQUIRE = "#B57CFF"  # Violet

# Exhaustive mapping from TrackState enum to state colors
STATE_COLORS: Dict[TrackState, str] = {
    TrackState.SEARCH: COLOR_SEARCH,
    TrackState.ACQUIRE: COLOR_ACQUIRE,
    TrackState.TRACK: COLOR_TRACK,
    TrackState.LOST: COLOR_LOST,
    TrackState.REACQUIRE: COLOR_REACQUIRE,
}

# Runtime assert that set(STATE_COLORS.keys()) == set(TrackState)
assert set(STATE_COLORS.keys()) == set(TrackState), (
    f"STATE_COLORS must exhaustively map all TrackState enum members. "
    f"Expected {set(TrackState)}, got {set(STATE_COLORS.keys())}"
)

# All defined hex colors for cross-checking with QSS
ALL_HEX_COLORS = {
    BG_ROOT,
    BG_PANEL,
    BG_INSET,
    BG_RAISED,
    LINE,
    LINE_STRONG,
    TEXT_0,
    TEXT_1,
    TEXT_2,
    OFF,
    COLOR_TRACK,
    COLOR_ACQUIRE,
    COLOR_SEARCH,
    COLOR_LOST,
    COLOR_REACQUIRE,
}
