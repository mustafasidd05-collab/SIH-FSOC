"""core/contracts.py -- source of truth for every data shape that crosses a module boundary.

This file is the contract between sim/, disturbance/, tracking/, control/, ui/ and
telemetry/. Never change a dataclass here without updating every consumer in the same
task and calling it out explicitly.

Units convention (applies to every field in this file):
    - angles ........ radians
    - lengths/dists . meters
    - time .......... seconds
    - pixel coords .. integer pixels, origin at the TOP-LEFT of the image
    - image data .... uint8, BGR, shape (height, width, 3), row-major (numpy default)
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from enum import Enum

import numpy as np


class TrackState(Enum):
    """Tracking state machine state (see AGENTS.md section 3).

    SEARCH -> ACQUIRE -> TRACK -> LOST -> REACQUIRE -> TRACK. LOST reverts to
    SEARCH after a timeout (stale filter is discarded rather than extrapolating
    forever).
    """

    SEARCH = "SEARCH"
    ACQUIRE = "ACQUIRE"
    TRACK = "TRACK"
    LOST = "LOST"
    REACQUIRE = "REACQUIRE"


@dataclass(frozen=True)
class CameraState:
    """Virtual pan-tilt camera pose and optics at a given instant.

    pan_rad / tilt_rad are the current gimbal angles. The *min/*max fields are the
    hard saturation bounds the control/ PID loop must respect -- never clamp inside
    control/ with locally hardcoded values; read them from the contract.

    fov_h_rad and fov_v_rad are the FULL horizontal and vertical field of view of the
    sensor (not diagonal, not half-angles), each in radians.
    """

    pan_rad: float
    tilt_rad: float
    pan_min_rad: float
    pan_max_rad: float
    tilt_min_rad: float
    tilt_max_rad: float
    fov_h_rad: float
    fov_v_rad: float
    width_px: int
    height_px: int


@dataclass(frozen=True)
class SimFrame:
    """One rendered frame leaving the sim/ pipeline.

    image is the disturbed camera image (sensor noise already injected by
    disturbance/ at integration time). camera is the pose/optics that produced it.
    """

    frame_id: int
    timestamp_s: float
    image: np.ndarray
    camera: CameraState


@dataclass(frozen=True)
class TargetState:
    """Ground-truth state of one optical beacon. world_pos is in the scene's
    world frame (x, y, z meters). az_rad / el_rad / range_m are the beacon's
    position relative to the camera boresight: azimuth (positive = right of
    boresight), elevation (positive = above boresight), and slant range.
    """

    target_id: int
    world_pos: tuple[float, float, float]
    az_rad: float
    el_rad: float
    range_m: float
    visible: bool


@dataclass(frozen=True)
class TrackResult:
    """One tracking-cycle output from tracking/.

    error_px is the offset of the detected beacon centroid from the FRAME BORESIGHT
    (image center, width_px/2, height_px/2), NOT raw pixel coordinates: error_px =
    (centroid_x - width/2, centroid_y - height/2). This is the quantity control/
    feeds its PID loop directly, so its sign/meaning is contract-critical.

    bbox_px is the axis-aligned detection box (x, y, w, h) in raw top-left-origin
    pixel coordinates.
    """

    frame_id: int
    timestamp_s: float
    state: TrackState
    centroid_px: tuple[float, float]
    bbox_px: tuple[float, float, float, float]
    confidence: float
    error_px: tuple[float, float]


@dataclass(frozen=True)
class TelemetryPacket:
    """One telemetry record consumed by ui/ (live dashboard) and telemetry/
    (aggregation + performance-log export).

    lock_fraction is a rolling 0..1 measure of lock quality (e.g. fraction of frames
    in TRACK over a lookback window). acquisition_time_s counts from the first SEARCH
    frame to entering TRACK (set when acquisition completes, NaN until then).
    """

    frame_id: int
    timestamp_s: float
    fps: float
    track_state: TrackState
    error_px: tuple[float, float]
    error_az_rad: float
    error_el_rad: float
    lock_fraction: float
    acquisition_time_s: float
    loop_time_s: float


__all__ = [
    "FrozenInstanceError",
    "TrackState",
    "CameraState",
    "SimFrame",
    "TargetState",
    "TrackResult",
    "TelemetryPacket",
]