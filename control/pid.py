"""control/pid.py -- PID controller for pan and tilt axes with anti-windup and derivative filtering.

Gain constants are defined as named module-level constants.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

__all__ = [
    "DEFAULT_KP_PAN",
    "DEFAULT_KI_PAN",
    "DEFAULT_KD_PAN",
    "DEFAULT_KP_TILT",
    "DEFAULT_KI_TILT",
    "DEFAULT_KD_TILT",
    "DEFAULT_INTEGRAL_MAX",
    "DEFAULT_MAX_OUTPUT_STEP",
    "PID1D",
    "PanTiltPID",
]

# Named gain constants (units: rad/px for Kp, rad/(px*s) for Ki, rad*s/px for Kd)
# 1 pixel ~ 0.00078 rad for 640px @ 0.5 rad FOV.
DEFAULT_KP_PAN: float = 0.0003
DEFAULT_KI_PAN: float = 0.00001
DEFAULT_KD_PAN: float = 0.00001

DEFAULT_KP_TILT: float = 0.0003
DEFAULT_KI_TILT: float = 0.00001
DEFAULT_KD_TILT: float = 0.00001

# Anti-windup limit for integrated error term (units: px*seconds)
DEFAULT_INTEGRAL_MAX: float = 100.0

# Maximum single-step output delta limit (units: radians per frame step)
# 0.003 rad ~ 3.84 pixels per step max gimbal velocity limit (~6.8 deg/s)
DEFAULT_MAX_OUTPUT_STEP: float = 0.003


@dataclass
class PID1D:
    """Single-axis PID controller with integral clamping (anti-windup) and derivative filtering."""

    kp: float
    ki: float
    kd: float
    integral_limit: float = DEFAULT_INTEGRAL_MAX
    max_output_step: float = DEFAULT_MAX_OUTPUT_STEP
    d_filter_alpha: float = 0.25  # Low-pass filter coefficient for derivative

    _integral: float = 0.0
    _prev_error: float | None = None
    _d_filtered: float = 0.0

    def reset(self) -> None:
        """Reset integral accumulation, derivative history, and filter state."""
        self._integral = 0.0
        self._prev_error = None
        self._d_filtered = 0.0

    def update(self, error: float, dt: float, clamped: bool = False) -> float:
        """Compute PID output step for a given error and timestep dt (seconds).

        If clamped is True (e.g. joint hit saturation limit), integral accumulation
        is frozen to prevent windup.
        """
        if dt <= 0.0 or not math.isfinite(error):
            return 0.0

        # Derivative calculation with exponential moving average low-pass filter
        if self._prev_error is not None:
            raw_d = (error - self._prev_error) / dt
            self._d_filtered = self.d_filter_alpha * raw_d + (1.0 - self.d_filter_alpha) * self._d_filtered
        else:
            self._d_filtered = 0.0
        self._prev_error = error

        # Integral accumulation with anti-windup clamping
        if not clamped:
            self._integral += error * dt
            if self.integral_limit > 0.0:
                self._integral = max(-self.integral_limit, min(self.integral_limit, self._integral))

        # PID terms sum
        p_term = self.kp * error
        i_term = self.ki * self._integral
        d_term = self.kd * self._d_filtered

        output = p_term + i_term + d_term

        # Output saturation limit
        if self.max_output_step > 0.0:
            output = max(-self.max_output_step, min(self.max_output_step, output))

        return output


class PanTiltPID:
    """Combined 2-axis PID controller for pan and tilt axes."""

    def __init__(
        self,
        kp_pan: float = DEFAULT_KP_PAN,
        ki_pan: float = DEFAULT_KI_PAN,
        kd_pan: float = DEFAULT_KD_PAN,
        kp_tilt: float = DEFAULT_KP_TILT,
        ki_tilt: float = DEFAULT_KI_TILT,
        kd_tilt: float = DEFAULT_KD_TILT,
        integral_limit: float = DEFAULT_INTEGRAL_MAX,
        max_output_step: float = DEFAULT_MAX_OUTPUT_STEP,
    ) -> None:
        self.pan_pid = PID1D(
            kp=kp_pan,
            ki=ki_pan,
            kd=kd_pan,
            integral_limit=integral_limit,
            max_output_step=max_output_step,
        )
        self.tilt_pid = PID1D(
            kp=kp_tilt,
            ki=ki_tilt,
            kd=kd_tilt,
            integral_limit=integral_limit,
            max_output_step=max_output_step,
        )

    def reset(self) -> None:
        """Reset both pan and tilt PID controllers."""
        self.pan_pid.reset()
        self.tilt_pid.reset()

    def update(
        self,
        error_px: tuple[float, float],
        dt: float,
        pan_clamped: bool = False,
        tilt_clamped: bool = False,
    ) -> tuple[float, float]:
        """Compute (delta_pan_rad, delta_tilt_rad) from TrackResult.error_px.

        Sign convention:
        - error_px.x > 0 (target right of boresight) -> delta_pan > 0 (rotate right)
        - error_px.y < 0 (target above boresight) -> delta_tilt > 0 (rotate up)
        """
        err_x, err_y = error_px
        delta_pan = +self.pan_pid.update(err_x, dt, clamped=pan_clamped)
        delta_tilt = -self.tilt_pid.update(err_y, dt, clamped=tilt_clamped)
        return delta_pan, delta_tilt
