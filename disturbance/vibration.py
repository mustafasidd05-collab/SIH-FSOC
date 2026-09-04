"""disturbance/vibration.py -- platform vibration as a correlated random-walk shift.

The whole frame is translated by a 2-D displacement drawn from an
Ornstein-Uhlenbeck (first-order Gauss-Markov) process:

    d_{t+1} = rho * d_t + sigma * sqrt(1 - rho^2) * eps,   rho = exp(-dt / tau)

This is the "damped random walk" of real platform vibration: it is bounded
(stationary std = ``displacement_sigma_px``, so it stays inside a few sigma
instead of drifting away), and it has memory -- displacement at frame t+1 is
a blend of the previous displacement and a new random kick, with correlation
time ``tau_s``. White per-frame jitter was rejected on purpose: vibration
has memory, and uncorrelated jitter looks like sensor glitches, not platform
motion. Scope call for the report: a single-axis scalar OU process per axis
stands in for the full multi-modal resonance spectrum of the mount; this
captures wander magnitude, boundedness and temporal correlation, which is
what the tracker and PID loop actually experience.

The shift is applied with a sub-pixel affine translation
(``cv2.warpAffine``, INTER_LINEAR, BORDER_REPLICATE), so even mild profiles
produce real sub-pixel motion instead of quantized frame snaps. The first
call after construction/reset draws the displacement directly from the
stationary distribution (``N(0, sigma^2)`` per axis) instead of ramping up
from zero, so a clip is statistically stationary from its first frame.

Range guide (displacement sigma in px, correlation time in s):
    displacement_sigma_px  mild 0.4   moderate 1.5  severe 3.5
    tau_s                  mild 0.05  moderate 0.2  severe 0.8
"""

from dataclasses import replace

import cv2
import numpy as np

from core.contracts import SimFrame


class VibrationModel:
    """Stateful per-frame platform-vibration injector.

    Call with a SimFrame; returns a new SimFrame whose image has been shifted
    by the current OU displacement. The displacement state carries across
    calls. ``timestamp_s`` differences drive the update rate (falling back to
    ``dt_fallback_s`` on the first frame or when timestamps do not advance),
    so the process stays time-consistent at any clip frame rate.

    Parameters
    ----------
    displacement_sigma_px : float
        Stationary std of the per-axis displacement, in px. Mild 0.4 (sub-pixel
        tremor) .. severe 3.5 (several-pixel platform wander).
    tau_s : float
        Correlation time of the OU process in seconds. Memory length of the
        walk; mild 0.05 (fast servo tremor) .. severe 0.8 (slow drift).
    dt_fallback_s : float
        Seconds assumed per frame when timestamps are flat (e.g. frame 0).
    seed : int | None
        Seed for the internal RNG.
    """

    def __init__(
        self,
        displacement_sigma_px: float = 1.5,
        tau_s: float = 0.2,
        dt_fallback_s: float = 1.0 / 60.0,
        seed: int | None = None,
    ) -> None:
        if displacement_sigma_px < 0:
            raise ValueError("displacement_sigma_px must be >= 0")
        if tau_s <= 0:
            raise ValueError("tau_s must be > 0")
        if dt_fallback_s <= 0:
            raise ValueError("dt_fallback_s must be > 0")
        self.displacement_sigma_px = displacement_sigma_px
        self.tau_s = tau_s
        self.dt_fallback_s = dt_fallback_s
        self._rng = np.random.default_rng(seed)
        self._displacement = np.zeros(2, dtype=np.float64)
        self._last_timestamp_s: float | None = None
        self._first_call = True

    @property
    def offset_px(self) -> tuple[float, float]:
        """Current (x, y) displacement in px -- read for tests/telemetry."""
        return (float(self._displacement[0]), float(self._displacement[1]))

    def reset(self, seed: int | None = None) -> None:
        """Re-seed the RNG (if given) and zero the displacement state."""
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._displacement = np.zeros(2, dtype=np.float64)
        self._last_timestamp_s = None
        self._first_call = True

    def __call__(self, frame: SimFrame) -> SimFrame:
        if self._last_timestamp_s is None or frame.timestamp_s <= self._last_timestamp_s:
            dt = self.dt_fallback_s
        else:
            dt = frame.timestamp_s - self._last_timestamp_s
        self._last_timestamp_s = frame.timestamp_s

        if self._first_call:
            self._first_call = False
            self._displacement = (
                self.displacement_sigma_px * self._rng.standard_normal(2)
            )
        else:
            rho = np.exp(-dt / self.tau_s)
            kick = np.sqrt(1.0 - rho * rho) * self.displacement_sigma_px * self._rng.standard_normal(2)
            self._displacement = rho * self._displacement + kick

        h, w = frame.image.shape[:2]
        m = np.float32([[1.0, 0.0, self._displacement[0]], [0.0, 1.0, self._displacement[1]]])
        img = cv2.warpAffine(
            frame.image, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
        )
        return replace(frame, image=img)