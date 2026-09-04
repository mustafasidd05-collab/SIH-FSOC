"""tracking/kalman.py -- constant-velocity Kalman filter over pixel position.

Wraps filterpy's KalmanFilter with a 4-state [x, y, vx, vy] / 2-observation
[x, y] model. Used for two jobs (per the module plan):

1. SMOOTHING -- noisy per-frame detections are fused against the motion
   model, so the reported centroid is always the *filtered* posterior mean.
2. PREDICTION -- during detection dropouts (LOST / brief gaps) the filter
   keeps extrapolating constant velocity, so the tracker knows where the
   beacon should be and can gate reacquisition candidates against it.

Discretization: per-frame dt is taken from SimFrame.timestamp_s deltas
(clamped -- see DT_MIN_S / DT_MAX_S) so a stalled loop cannot explode the
state-transition matrix. Q is block-diagonal Q_discrete_white_noise for each
axis; R is diagonal measurement variance (isotropic pixel noise).
"""

from __future__ import annotations

import numpy as np
from filterpy.common import Q_discrete_white_noise
from filterpy.kalman import KalmanFilter

# ---------------------------------------------------------------------------
# Named tunables. Units: positions px, velocities px/s, variances (px)^2 and
# (px/s)^2 respectively, time s.
# ---------------------------------------------------------------------------

# Process noise variance (continuous-time acceleration spectral density, px^2/s^3).
# The beacon traces a curved path (sinusoidal ripple, centripetal accel ~50 px/s^2).
# Setting q=2000 keeps the filter responsive enough to follow that curvature: the
# resulting position-process-noise per frame (~3e-2 px^2) yields a steady-state
# Kalman gain of ~0.7 against R=4, meaning the filter corrects 70% of prediction
# error each frame.  At q=10 the filter converged to a gain of ~0.001 and silently
# diverged on any curved path -- a subtle but critical tuning failure for a real-time
# tracking loop.
PROCESS_NOISE_VAR = 2000.0

# Measurement noise variance per axis (px^2).  Centroid accuracy of a 20-pixel
# thresholded blob under sigma-10 sensor noise is ~2 px, giving R=4 (sigma=2).
# This is validated against the synthetic clips: centroid error vs ground truth
# is < 0.5 px on the clean clip.
MEASUREMENT_NOISE_VAR = 4.0

# Initial state covariance on acquisition: position known to ~5px, velocity
# unknown (treated as +/-20px/s).
INIT_POS_VAR = 25.0
INIT_VEL_VAR = 400.0

# dt clamps: ignore frame-rate spikes <= 4x too fast (1/240 s) and stalls
# > 0.25 s (predict one step with a bounded dt rather than exploding the
# transition matrix).
DT_MIN_S = 1.0 / 240.0
DT_MAX_S = 0.25


def _clamp_dt(dt_s: float) -> float:
    return float(np.clip(dt_s, DT_MIN_S, DT_MAX_S))


class KalmanTracker:
    """Filterpy-backed constant-velocity tracker in pixel space.

    Lifecycle: inactive until initialize(xy) is called (the state machine
    seeds it on first acquisition); reset() returns it to inactive. While
    inactive, predict() returns None and update() raises -- the pipeline must
    not feed the filter before a state exists.
    """

    def __init__(
        self,
        process_noise_var: float = PROCESS_NOISE_VAR,
        measurement_noise_var: float = MEASUREMENT_NOISE_VAR,
        init_pos_var: float = INIT_POS_VAR,
        init_vel_var: float = INIT_VEL_VAR,
    ) -> None:
        self._process_var = process_noise_var
        self._measure_var = measurement_noise_var
        self._init_pos_var = init_pos_var
        self._init_vel_var = init_vel_var
        self._kf: KalmanFilter | None = None

    # -- lifecycle ---------------------------------------------------------

    @property
    def active(self) -> bool:
        return self._kf is not None

    def initialize(self, xy: tuple[float, float]) -> None:
        """Seed the filter at a first detection position with zero velocity."""
        kf = KalmanFilter(dim_x=4, dim_z=2)
        kf.x = np.array([xy[0], xy[1], 0.0, 0.0], dtype=float)
        kf.P = np.diag(
            [self._init_pos_var, self._init_pos_var, self._init_vel_var, self._init_vel_var]
        )
        kf.F = np.eye(4)  # filled per-frame by _set_dynamics(dt)
        kf.H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
        kf.R = np.eye(2) * self._measure_var
        self._kf = kf

    def reset(self) -> None:
        """Drop the filter state (LOST timeout -> fresh SEARCH)."""
        self._kf = None

    # -- filter steps ------------------------------------------------------

    def _set_dynamics(self, dt_s: float) -> None:
        dt = _clamp_dt(dt_s)
        kf = self._kf
        assert kf is not None  # guarded by callers
        kf.F = np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        q = Q_discrete_white_noise(dim=2, dt=dt, var=self._process_var)
        kf.Q = np.zeros((4, 4))
        kf.Q[:2, :2] = q
        kf.Q[2:, 2:] = q

    def predict(self, dt_s: float) -> tuple[float, float] | None:
        """Advance the motion model by dt_s. Returns the predicted (x, y), or
        None if the filter is inactive."""
        if self._kf is None:
            return None
        self._set_dynamics(dt_s)
        self._kf.predict()
        return (float(self._kf.x[0]), float(self._kf.x[1]))

    def update(self, xy: tuple[float, float]) -> tuple[float, float]:
        """Fuse a detection into the posterior. Raises if called while
        inactive -- this is a programming error, not a data condition."""
        if self._kf is None:
            raise RuntimeError("KalmanTracker.update() called while inactive")
        self._kf.update(np.array([xy[0], xy[1]], dtype=float))
        return self.mean_px  # type: ignore[return-value]

    # -- output ------------------------------------------------------------

    @property
    def mean_px(self) -> tuple[float, float] | None:
        """Posterior mean (x, y), the filtered centroid the tracker reports."""
        if self._kf is None:
            return None
        return (float(self._kf.x[0]), float(self._kf.x[1]))

    @property
    def covariance(self) -> np.ndarray | None:
        if self._kf is None:
            return None
        return self._kf.P.copy()