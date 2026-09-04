"""sim/camera.py -- virtual pan-tilt camera: rotation, gnomonic projection, visibility.

Frame conventions (the math this module defends in the technical report):

    World frame: origin at the gimbal pivot. +x right, +y up, +z forward
    (boresight direction when pan = tilt = 0).

    Absolute target direction (from az_rad/el_rad in TargetState):
        d = (cos(el) * sin(az), sin(el), cos(el) * cos(az))
    with az positive = right of world +z, el positive = up.

    Pan rotates the head about world +y (positive = right). Tilt rotates the
    head about the pan axis's local x (positive = up). Camera-to-world
    composition: R = R_y(pan) * R_x(-tilt), so the boresight vector is
    (cos(tilt)*sin(pan), sin(tilt), cos(tilt)*cos(pan)) -- the gimbal pan/tilt
    angles ARE the azimuth/elevation of the boresight in the world frame, which
    is what makes the "camera pointed exactly at the target" case collapse to
    zero error.

    Boresight-relative angles are recovered exactly (not by subtraction):
        v_cam = R_x(tilt) * R_y(-pan) * v_world
        az_rel = atan2(v_cam.x, v_cam.z)
        el_rel = atan2(v_cam.y, hypot(v_cam.x, v_cam.z))
    This reduces to az_rel = az_abs - pan exactly when tilt = 0 (hand-verified:
    R_y(-pan) of the target direction leaves y untouched and folds x/z into
    sin/cos of the difference) and stays physically correct at large angles --
    the sign/axis error this design is meant to avoid.

    Gnomonic (pinhole) projection, the mapping a real lens performs:
        fx = (W / 2) / tan(fov_h / 2)        fy = (H / 2) / tan(fov_v / 2)
        px = W / 2 + fx * tan(az_rel)        py = H / 2 - fy * tan(el_rel)
    Pixel y grows downward, so a positive elevation (above boresight) maps to a
    SMALLER pixel row -- hence the minus sign. Sanity: az_rel = fov_h / 2
    projects to px = W exactly (edge of frame, by construction).

    Visibility: range > 0 and |az_rel| <= fov_h / 2 and |el_rel| <= fov_v / 2.
    Equivalent to the pixel test under gnomonic projection (monotone tan on the
    open domain), evaluated in angle space so it stays finite for targets
    behind the camera.

All angles are radians; all pixels are float top-left-origin coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from core.contracts import CameraState, TargetState

__all__ = [
    "ClampReport",
    "boresight_az_el",
    "project_azel",
    "project_target",
    "is_visible",
    "command_pan_tilt",
]


@dataclass(frozen=True)
class ClampReport:
    """Which gimbal axes were clipped by the last command_pan_tilt call.

    False means the command was already inside the joint's hard limits from
    core/contracts.CameraState and was applied verbatim.
    """

    pan_clamped: bool
    tilt_clamped: bool


def boresight_az_el(
    az_abs_rad: float,
    el_abs_rad: float,
    pan_rad: float,
    tilt_rad: float,
) -> tuple[float, float]:
    """Boresight-relative (az_rel, el_rel) for an absolute az/el at a given gimbal pose.

    Exact rotation recovery -- see module docstring. None of the inputs are
    clamped here; clamping happens only in command_pan_tilt.
    """
    cos_el = float(np.cos(el_abs_rad))
    v_world = np.array(
        [
            cos_el * float(np.sin(az_abs_rad)),
            float(np.sin(el_abs_rad)),
            cos_el * float(np.cos(az_abs_rad)),
        ]
    )
    cp, sp = float(np.cos(pan_rad)), float(np.sin(pan_rad))
    ct, st = float(np.cos(tilt_rad)), float(np.sin(tilt_rad))

    v_pan = (v_world[0] * cp - v_world[2] * sp, v_world[1], v_world[0] * sp + v_world[2] * cp)
    v_cam = (
        v_pan[0],
        v_pan[1] * ct - v_pan[2] * st,
        v_pan[1] * st + v_pan[2] * ct,
    )

    az_rel = float(np.arctan2(v_cam[0], v_cam[2]))
    el_rel = float(np.arctan2(v_cam[1], np.hypot(v_cam[0], v_cam[2])))
    return az_rel, el_rel


def project_azel(
    az_rel_rad: float,
    el_rel_rad: float,
    camera: CameraState,
) -> tuple[float, float]:
    """Gnomonic projection of boresight-relative angles onto the frame.

    Returns (px, py) as FLOAT pixel coordinates, origin top-left. The caller is
    responsible for checking is_visible first; tan is monotone on the FOV
    domain so in-FOV targets never leave the frame.
    """
    fx = (camera.width_px / 2.0) / np.tan(camera.fov_h_rad / 2.0)
    fy = (camera.height_px / 2.0) / np.tan(camera.fov_v_rad / 2.0)
    px = camera.width_px / 2.0 + fx * float(np.tan(az_rel_rad))
    py = camera.height_px / 2.0 - fy * float(np.tan(el_rel_rad))
    return float(px), float(py)


def project_target(
    target: TargetState,
    camera: CameraState,
) -> tuple[float, float]:
    """Project a TargetState (its az_rad/el_rad are boresight-relative) to pixels."""
    return project_azel(target.az_rad, target.el_rad, camera)


def is_visible(
    az_rel_rad: float,
    el_rel_rad: float,
    camera: CameraState,
) -> bool:
    """Whether a boresight-relative direction falls inside the camera FOV."""
    return (
        abs(az_rel_rad) <= camera.fov_h_rad / 2.0
        and abs(el_rel_rad) <= camera.fov_v_rad / 2.0
    )


def command_pan_tilt(
    camera: CameraState,
    pan_cmd_rad: float,
    tilt_cmd_rad: float,
) -> tuple[CameraState, ClampReport]:
    """Command a new pan/tilt; clamp to the contract's gimbal limits.

    Limits come from the CameraState fields (pan_min_rad ... tilt_max_rad),
    never from hardcoded values here. At-bound commands count as in-range; a
    clamp is only reported when the clip actually changed the command.
    """
    pan_clamped = pan_cmd_rad < camera.pan_min_rad or pan_cmd_rad > camera.pan_max_rad
    tilt_clamped = tilt_cmd_rad < camera.tilt_min_rad or tilt_cmd_rad > camera.tilt_max_rad

    pan_out = min(max(pan_cmd_rad, camera.pan_min_rad), camera.pan_max_rad)
    tilt_out = min(max(tilt_cmd_rad, camera.tilt_min_rad), camera.tilt_max_rad)

    commanded = replace(
        camera,
        pan_rad=float(pan_out),
        tilt_rad=float(tilt_out),
    )
    return commanded, ClampReport(pan_clamped=pan_clamped, tilt_clamped=tilt_clamped)