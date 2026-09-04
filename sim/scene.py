"""sim/scene.py -- configurable virtual scene: beacon definitions and target motion.

Motion models are evaluated ANALYTICALLY from accumulated scene time, never by
integrating a per-step velocity. That means frame rate cannot introduce drift:
a linear target at t = 10.0 s is at exactly az0 + rate * 10.0, and a sinusoidal
target at t = 1/(4f) is at exactly az0 + amp. The cost is free (a couple of
trig calls per target) and the reproducibility is what the performance log
wants.

Motion models operate in az/el angle space (the units TargetState carries) --
not raw pixels -- so a scene behaves identically regardless of the camera
optics attached to it. Range_m is a free knob (set per beacon).

Config is dictionary-driven (JSON/route-table friendly), deserialized by the
from_dict classmethods so the same config that comes from a config panel or
CLI flag can build a Scene without bespoke wiring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from core.contracts import CameraState, TargetState
from sim.camera import boresight_az_el, is_visible

__all__ = [
    "LinearMotionConfig",
    "SinusoidalMotionConfig",
    "BeaconConfig",
    "SceneConfig",
    "Scene",
]


@dataclass(frozen=True)
class LinearMotionConfig:
    """Constant-velocity motion in az/el space: az(t) = az0 + az_rate * t."""

    az0_rad: float
    el0_rad: float
    az_rate_rad_s: float
    el_rate_rad_s: float

    @classmethod
    def from_dict(cls, d: dict) -> LinearMotionConfig:
        return cls(
            az0_rad=float(d["az0_rad"]),
            el0_rad=float(d["el0_rad"]),
            az_rate_rad_s=float(d.get("az_rate_rad_s", 0.0)),
            el_rate_rad_s=float(d.get("el_rate_rad_s", 0.0)),
        )

    def az_el_at(self, t: float) -> tuple[float, float]:
        return self.az0_rad + self.az_rate_rad_s * t, self.el0_rad + self.el_rate_rad_s * t


@dataclass(frozen=True)
class SinusoidalMotionConfig:
    """Sinusoidal motion about an offset in az/el space.

    az(t) = az0 + az_amp * sin(2*pi*az_freq*t + az_phase)
    el(t) = el0 + el_amp * sin(2*pi*el_freq*t + el_phase)
    """

    az0_rad: float
    el0_rad: float
    az_amp_rad: float
    az_freq_hz: float
    az_phase_rad: float
    el_amp_rad: float
    el_freq_hz: float
    el_phase_rad: float

    @classmethod
    def from_dict(cls, d: dict) -> SinusoidalMotionConfig:
        return cls(
            az0_rad=float(d["az0_rad"]),
            el0_rad=float(d["el0_rad"]),
            az_amp_rad=float(d.get("az_amp_rad", 0.0)),
            az_freq_hz=float(d.get("az_freq_hz", 0.0)),
            az_phase_rad=float(d.get("az_phase_rad", 0.0)),
            el_amp_rad=float(d.get("el_amp_rad", 0.0)),
            el_freq_hz=float(d.get("el_freq_hz", 0.0)),
            el_phase_rad=float(d.get("el_phase_rad", 0.0)),
        )

    def az_el_at(self, t: float) -> tuple[float, float]:
        az = self.az0_rad + self.az_amp_rad * math.sin(
            2.0 * math.pi * self.az_freq_hz * t + self.az_phase_rad
        )
        el = self.el0_rad + self.el_amp_rad * math.sin(
            2.0 * math.pi * self.el_freq_hz * t + self.el_phase_rad
        )
        return az, el


_MotionKind = Literal["linear", "sinusoidal"]
_RoleKind = Literal["primary", "distractor"]


@dataclass(frozen=True)
class BeaconConfig:
    """One beacon in the scene: identity + range + a discriminated motion model + role/appearance."""

    target_id: int
    range_m: float
    motion: _MotionKind
    role: _RoleKind = "primary"
    beacon_radius_px: float | None = None
    peak_intensity: float | None = None
    linear: LinearMotionConfig | None = None
    sinusoidal: SinusoidalMotionConfig | None = None

    @classmethod
    def from_dict(cls, d: dict) -> BeaconConfig:
        """Build from a dict; motion params may be nested under the motion key or flat."""
        motion = d["motion"]
        role = d.get("role", "primary")
        if role not in ("primary", "distractor"):
            raise ValueError(f"unknown role {role!r}; choose 'primary' or 'distractor'")
        radius_px = float(d["beacon_radius_px"]) if "beacon_radius_px" in d and d["beacon_radius_px"] is not None else None
        intensity = float(d["peak_intensity"]) if "peak_intensity" in d and d["peak_intensity"] is not None else None

        if motion == "linear":
            inner = LinearMotionConfig.from_dict(d.get("linear", d))
            return cls(
                target_id=int(d["target_id"]),
                range_m=float(d.get("range_m", 1000.0)),
                motion=motion,
                role=role,
                beacon_radius_px=radius_px,
                peak_intensity=intensity,
                linear=inner,
            )
        if motion == "sinusoidal":
            inner = SinusoidalMotionConfig.from_dict(d.get("sinusoidal", d))
            return cls(
                target_id=int(d["target_id"]),
                range_m=float(d.get("range_m", 1000.0)),
                motion=motion,
                role=role,
                beacon_radius_px=radius_px,
                peak_intensity=intensity,
                sinusoidal=inner,
            )
        raise ValueError(f"unknown motion type {motion!r}")


@dataclass(frozen=True)
class SceneConfig:
    """Full scene description: the ordered tuple of beacons."""

    beacons: tuple[BeaconConfig, ...]

    @classmethod
    def from_dict(cls, d: dict) -> SceneConfig:
        beacons = tuple(BeaconConfig.from_dict(b) for b in d["beacons"])
        return cls(beacons=beacons)


class Scene:
    """Owns the scene clock and produces absolute TargetState ground truth.

    Wire-up: call update_camera() whenever the gimbal moves (or before the
    first snapshot), then snapshot() to get the targets for this instant.
    t_s advances by dt on each step(); it is the API the control loop will
    drive at run time.
    """

    def __init__(self, config: SceneConfig) -> None:
        self._config = config
        self._t_s: float = 0.0
        self._camera: CameraState | None = None
        self._frame_id: int = 0

    @property
    def t_s(self) -> float:
        """Accumulated scene time (seconds, starts at 0)."""
        return self._t_s

    @property
    def frame_id(self) -> int:
        return self._frame_id

    @property
    def primary_target_id(self) -> int:
        """target_id of the primary beacon (first beacon with role 'primary', or first beacon)."""
        for beacon in self._config.beacons:
            if beacon.role == "primary":
                return beacon.target_id
        return self._config.beacons[0].target_id if self._config.beacons else 0

    def get_beacon_config(self, target_id: int) -> BeaconConfig | None:
        """Look up BeaconConfig for a target_id."""
        for b in self._config.beacons:
            if b.target_id == target_id:
                return b
        return None

    def step(self, dt: float) -> None:
        """Advance the scene clock by dt seconds (dt >= 0)."""
        if dt < 0.0:
            raise ValueError(f"dt must be >= 0, got {dt}")
        self._t_s += dt

    def update_camera(self, camera: CameraState) -> None:
        """Attach the current gimbal pose for the next snapshot()."""
        self._camera = camera

    def snapshot(self) -> list[TargetState]:
        """Ground-truth TargetState for every beacon this instant.

        Each target's az_rad/el_rad are boresight-relative (computed via the
        exact rotation in sim.camera), visible is the FOV test, and world_pos
        is the absolute beacon position in the scene's world frame at the
        current scene time.
        """
        if self._camera is None:
            raise RuntimeError("update_camera() must be called before snapshot()")

        out: list[TargetState] = []
        for beacon in self._config.beacons:
            if beacon.motion == "linear":
                assert beacon.linear is not None
                az_abs, el_abs = beacon.linear.az_el_at(self._t_s)
            else:
                assert beacon.sinusoidal is not None
                az_abs, el_abs = beacon.sinusoidal.az_el_at(self._t_s)

            az_rel, el_rel = boresight_az_el(
                az_abs, el_abs, self._camera.pan_rad, self._camera.tilt_rad
            )
            visible = is_visible(az_rel, el_rel, self._camera)

            cos_el = math.cos(el_abs)
            world_pos = (
                beacon.range_m * cos_el * math.sin(az_abs),
                beacon.range_m * math.sin(el_abs),
                beacon.range_m * cos_el * math.cos(az_abs),
            )

            out.append(
                TargetState(
                    target_id=beacon.target_id,
                    world_pos=world_pos,
                    az_rad=az_rel,
                    el_rad=el_rel,
                    range_m=beacon.range_m,
                    visible=visible,
                )
            )
        return out