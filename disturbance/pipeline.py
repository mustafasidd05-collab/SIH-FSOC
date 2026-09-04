"""disturbance/pipeline.py -- composes turbulence, vibration and sensor noise.

tracking/ (or the integration loop) never touches the individual injectors:
it picks a named ``DisturbanceProfile`` out of ``PROFILES`` and either

    frame = apply_profile(sim_frame, PROFILES["moderate"], seed=123)   # single frame

or, for a continuous clip with correct temporal correlation, builds one
pipeline once and calls it per frame:

    pipe = make_pipeline(PROFILES["severe"], seed=123)
    while frame := sim.next():
        frame = pipe.apply(frame)

Composition order is physically motivated -- the optical field is perturbed
first (turbulence), then the platform shifts the formed image (vibration),
then the sensor quantizes and noises it (sensor noise). Reversing the order
would, for example, let detector noise get smeared by vibration, which is the
wrong causal chain.

Each model gets its own RNG derived from the shared seed (seed, seed+1,
seed+2), so the three disturbance streams are independent and reproducible.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from core.contracts import SimFrame

from .camera_motion_blur import CameraMotionBlurModel
from .occlusion import OcclusionModel
from .sensor_noise import SensorNoiseModel
from .turbulence import TurbulenceModel
from .vibration import VibrationModel


@dataclass(frozen=True)
class DisturbanceProfile:
    """One named, documented set of disturbance parameters.

    Each dict is passed to the corresponding model constructor as kwargs.
    Validated against the model constructors when a pipeline is built.
    """

    name: str
    turbulence: Mapping[str, Any]
    occlusion: Mapping[str, Any]
    camera_motion_blur: Mapping[str, Any]
    vibration: Mapping[str, Any]
    sensor_noise: Mapping[str, Any]


PROFILES: dict[str, DisturbanceProfile] = {
    "mild": DisturbanceProfile(
        name="mild",
        turbulence={"blur_sigma_px": 0.4, "scint_sigma": 0.05},
        occlusion={"num_clouds": 1, "speed_px_s": 20.0, "opacity": 0.2, "size_px": 40.0},
        camera_motion_blur={"blur_gain": 5.0, "max_kernel_size": 5},
        vibration={"displacement_sigma_px": 0.4, "tau_s": 0.05},
        sensor_noise={"snr_db": 35.0, "read_noise_fraction": 0.25},
    ),
    "moderate": DisturbanceProfile(
        name="moderate",
        turbulence={"blur_sigma_px": 1.2, "scint_sigma": 0.15},
        occlusion={"num_clouds": 2, "speed_px_s": 50.0, "opacity": 0.5, "size_px": 80.0},
        camera_motion_blur={"blur_gain": 15.0, "max_kernel_size": 9},
        vibration={"displacement_sigma_px": 1.5, "tau_s": 0.2},
        sensor_noise={"snr_db": 22.0, "read_noise_fraction": 0.30},
    ),
    "severe": DisturbanceProfile(
        name="severe",
        turbulence={"blur_sigma_px": 2.5, "scint_sigma": 0.35},
        occlusion={"num_clouds": 3, "speed_px_s": 90.0, "opacity": 0.8, "size_px": 150.0},
        camera_motion_blur={"blur_gain": 30.0, "max_kernel_size": 19},
        vibration={"displacement_sigma_px": 3.5, "tau_s": 0.8},
        sensor_noise={"snr_db": 12.0, "read_noise_fraction": 0.40},
    ),
}


class DisturbancePipeline:
    """Stateful composite: holds all disturbance models and runs them in order.

    Parameters
    ----------
    profile : str | DisturbanceProfile
        Key into ``PROFILES`` or an explicit profile object.
    seed : int | None
        Seed; each model derives its own independent stream from it.
    """

    def __init__(self, profile: str | DisturbanceProfile, seed: int | None = None) -> None:
        if isinstance(profile, str):
            if profile not in PROFILES:
                raise KeyError(f"unknown disturbance profile {profile!r}; choose from {sorted(PROFILES)}")
            profile = PROFILES[profile]
        if not isinstance(profile, DisturbanceProfile):
            raise TypeError("profile must be a str key into PROFILES or a DisturbanceProfile")
        self.profile = profile
        self.turbulence = TurbulenceModel(seed=seed, **profile.turbulence)
        self.occlusion = OcclusionModel(
            seed=None if seed is None else seed + 1, **profile.occlusion
        )
        self.camera_motion_blur = CameraMotionBlurModel(
            seed=None if seed is None else seed + 2, **profile.camera_motion_blur
        )
        self.vibration = VibrationModel(
            seed=None if seed is None else seed + 3, **profile.vibration
        )
        self.sensor_noise = SensorNoiseModel(
            seed=None if seed is None else seed + 4, **profile.sensor_noise
        )

    def apply(self, frame: SimFrame) -> SimFrame:
        """turbulence -> occlusion -> camera motion blur -> vibration -> sensor noise."""
        frame = self.turbulence(frame)
        frame = self.occlusion(frame)
        frame = self.camera_motion_blur(frame)
        frame = self.vibration(frame)
        return self.sensor_noise(frame)

    __call__ = apply

    def reset(self, seed: int | None = None) -> None:
        """Reset all models; re-seeding only if a seed is given."""
        self.turbulence.reset(seed)
        self.occlusion.reset(None if seed is None else seed + 1)
        self.camera_motion_blur.reset(None if seed is None else seed + 2)
        self.vibration.reset(None if seed is None else seed + 3)
        self.sensor_noise.reset(None if seed is None else seed + 4)


def make_pipeline(profile: str | DisturbanceProfile, seed: int | None = None) -> DisturbancePipeline:
    """Build a stateful pipeline for a named profile (use for continuous clips)."""
    return DisturbancePipeline(profile, seed=seed)


def apply_profile(
    frame: SimFrame, profile: str | DisturbanceProfile, seed: int | None = None
) -> SimFrame:
    """Apply a profile to one frame (fresh state, single call).

    For continuous clips with temporal correlation between frames, build a
    pipeline with :func:`make_pipeline` and call it once per frame instead.
    """
    return DisturbancePipeline(profile, seed=seed).apply(frame)