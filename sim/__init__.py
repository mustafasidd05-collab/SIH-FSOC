"""sim -- virtual scene package: scene, camera model, rasterizer.

Everything here depends only on core/contracts.py (plus numpy), per AGENTS.md
section 3. disturbance/ consumes sim/render output; tracking/ consumes
sim/camera projection semantics; control/ consumes sim/camera clamping.
"""

from sim.camera import ClampReport, boresight_az_el, command_pan_tilt, is_visible, project_azel, project_target
from sim.render import RenderConfig, render
from sim.scene import BeaconConfig, LinearMotionConfig, Scene, SceneConfig, SinusoidalMotionConfig

__all__ = [
    "ClampReport",
    "boresight_az_el",
    "command_pan_tilt",
    "is_visible",
    "project_azel",
    "project_target",
    "RenderConfig",
    "render",
    "BeaconConfig",
    "LinearMotionConfig",
    "Scene",
    "SceneConfig",
    "SinusoidalMotionConfig",
]