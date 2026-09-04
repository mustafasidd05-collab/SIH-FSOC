"""disturbance/sensor_noise.py -- Gaussian read noise + shot noise on pixels.

Two physical noise sources, both zero-mean so the mean brightness is
preserved within rounding:

1. Read noise: signal-independent Gaussian, std ``sigma_read``. This covers
   detector readout/amplification noise and the dark floor.
2. Shot noise: Poisson photon-count noise approximated by a Gaussian whose
   variance is proportional to the pixel intensity (the standard Gaussian
   approximation of Poisson for counts above ~10). Bright pixels (beacon)
   therefore jitter more than dark pixels (sky), which is the behaviour a
   real detector exhibits.

The profile is calibrated by an SNR-like parameter: ``snr_db`` is referenced
to the full-scale signal, i.e. the total one-sigma noise at mid-range is

    sigma_total = 255 / 10 ** (snr_db / 20)

at a reference intensity of 128 counts, with a fraction
``read_noise_fraction`` of that budget allocated to read noise and the rest
to the shot term (so the measured sigma on a flat 128 frame equals
``sigma_total`` within tolerance -- see the tests).

Range guide (SNR in dB, read fraction dimensionless):
    snr_db  mild 35 (sigma~4.5)  moderate 22 (sigma~20)  severe 12 (sigma~64)
    read_noise_fraction  mild 0.25  moderate 0.30  severe 0.40
"""

from dataclasses import replace

import numpy as np

from core.contracts import SimFrame


class SensorNoiseModel:
    """Stateless-per-pixel noise injector (each frame is an independent draw).

    Parameters
    ----------
    snr_db : float
        Signal-to-noise ratio in dB referenced to 255 counts full scale,
        evaluated at the reference intensity. 35 = clean science camera,
        22 = typical low-light, 12 = near detection limit.
    read_noise_fraction : float
        Fraction of the total noise budget (at the reference intensity)
        allocated to flat read noise; the remainder drives the
        intensity-proportional shot term.
    reference_intensity : float
        Counts at which the calibration is anchored (128 = mid-scale).
    seed : int | None
        Seed for the internal RNG.
    """

    def __init__(
        self,
        snr_db: float = 22.0,
        read_noise_fraction: float = 0.30,
        reference_intensity: float = 128.0,
        seed: int | None = None,
    ) -> None:
        if not 0.0 < read_noise_fraction < 1.0:
            raise ValueError("read_noise_fraction must be in (0, 1)")
        if reference_intensity <= 0:
            raise ValueError("reference_intensity must be > 0")
        self.snr_db = snr_db
        self.read_noise_fraction = read_noise_fraction
        self.reference_intensity = reference_intensity
        self._rng = np.random.default_rng(seed)

        self.sigma_total = 255.0 / (10.0 ** (self.snr_db / 20.0))
        self._sigma_read = self.sigma_total * read_noise_fraction
        # Shot variance is k * I; anchor it so that at I == reference_intensity
        # the total variance equals sigma_total^2:
        #   sigma_total^2 = sigma_read^2 + k * reference_intensity
        self._shot_gain = (
            self.sigma_total**2 * (1.0 - read_noise_fraction**2)
        ) / self.reference_intensity

    @property
    def sigma_read(self) -> float:
        """Flat read-noise std in counts."""
        return self._sigma_read

    def reset(self, seed: int | None = None) -> None:
        """Re-seed the RNG (if given). No other state exists."""
        if seed is not None:
            self._rng = np.random.default_rng(seed)

    def __call__(self, frame: SimFrame) -> SimFrame:
        img = frame.image.astype(np.float32)

        read = self._sigma_read * self._rng.standard_normal(size=img.shape)
        shot = np.sqrt(self._shot_gain * img) * self._rng.standard_normal(size=img.shape)

        out = np.rint(img + read + shot)
        return replace(frame, image=np.clip(out, 0, 255).astype(np.uint8))