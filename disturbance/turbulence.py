"""disturbance/turbulence.py -- atmospheric turbulence (simplified stand-in).

Simplified model, deliberately NOT a full phase-screen / Zernike Kolmogorov
simulation. Two observables that matter at FSOC coarse alignment are modelled:

1. Beam smear: the beacon image is convolved with a Gaussian PSF whose sigma
   is drawn per-frame from a uniform band around a nominal ``blur_sigma_px``.
   This stands in for the anisoplanatic spread of the short-exposure PSF.
2. Scintillation: an AR(1) process on log-amplitude (first-order Gauss-Markov,
   correlation time controlled by ``scint_rho``) produces a per-frame
   multiplicative brightness gain ``exp(x - sigma^2/2)`` (log-normal, mean 1).
   It modulates the whole frame uniformly: the dominant coarse-alignment
   observable is beacon-brightness fading, and uniform gain also bounds
   detector/sky background stats.

This is a defensible scope call for the technical report: beacons occupy many
pixels and a coarse PSF + gain model captures the tracking-relevant envelope
(smear size, fading depth, temporal correlation) without a multi-layer screen.
Fine-fringe speckle structure is deferred to future work.

Range guide (values are per-pixel, in px / dimensionless):
    blur_sigma_px      mild 0.4   moderate 1.2  severe 2.5
    scint_sigma        mild 0.05  moderate 0.15 severe 0.35
    scint_rho          fixed 0.9 in all profiles (slow fading, ~0.05 s memory)
"""

from dataclasses import replace
import math

import cv2
import numpy as np

from core.contracts import SimFrame


class TurbulenceModel:
    """Stateful per-frame turbulence injector.

    Call with a SimFrame; returns a new SimFrame whose image is the turbulated
    version (dtype uint8 BGR, same shape). frame_id / timestamp_s / camera are
    preserved by value and reference respectively. State (the AR(1) scintillation
    walk) carries across calls, so frames in a clip are temporally correlated.

    Parameters
    ----------
    blur_sigma_px : float
        Nominal Gaussian PSF sigma in px; each frame draws uniformly from
        ``blur_jitter_range`` around it.
    blur_jitter_range : tuple[float, float]
        Multiplicative band for the per-frame blur draw.
    scint_sigma : float
        Stationary standard deviation of the log-amplitude AR(1) process
        (dimensionless). Gains are ``exp(x - scint_sigma**2 / 2)`` so the mean
        gain is 1; sigma 0.05/0.15/0.35 roughly equals +/-5/15/35 % peak flicker.
    scint_rho : float
        AR(1) coefficient in (0, 1); the autocorrelation between successive
        frames decays as ``rho ** (dt / frame_period)``.
    seed : int | None
        Seed for the internal RNG. Same seed + same call sequence reproduces
        the exact same disturbance stream.
    """

    def __init__(
        self,
        blur_sigma_px: float = 1.2,
        blur_jitter_range: tuple[float, float] = (0.6, 1.4),
        scint_sigma: float = 0.15,
        scint_rho: float = 0.9,
        seed: int | None = None,
    ) -> None:
        if blur_sigma_px < 0:
            raise ValueError("blur_sigma_px must be >= 0")
        if not (0.0 < blur_jitter_range[0] <= blur_jitter_range[1]):
            raise ValueError("blur_jitter_range must be (lo, hi) with 0 < lo <= hi")
        if scint_sigma < 0:
            raise ValueError("scint_sigma must be >= 0")
        if not 0.0 < scint_rho < 1.0:
            raise ValueError("scint_rho must be in (0, 1)")
        self.blur_sigma_px = blur_sigma_px
        self.blur_jitter_range = blur_jitter_range
        self.scint_sigma = scint_sigma
        self.scint_rho = scint_rho
        self._rng = np.random.default_rng(seed)
        self._scint = 0.0

    def reset(self, seed: int | None = None) -> None:
        """Re-seed the RNG (if given) and zero the scintillation state."""
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._scint = 0.0

    def __call__(self, frame: SimFrame) -> SimFrame:
        img = frame.image.astype(np.float32)

        sigma = self.blur_sigma_px * float(self._rng.uniform(*self.blur_jitter_range))
        if sigma > 0.0:
            img = cv2.GaussianBlur(img, (0, 0), sigmaX=sigma, sigmaY=sigma)

        self._scint = (
            self.scint_rho * self._scint
            + math.sqrt(1.0 - self.scint_rho**2) * self.scint_sigma * float(self._rng.standard_normal())
        )
        gain = math.exp(self._scint - 0.5 * self.scint_sigma**2)

        img = np.rint(img * gain)
        return replace(frame, image=np.clip(img, 0, 255).astype(np.uint8))