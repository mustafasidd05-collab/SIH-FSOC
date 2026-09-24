/**
 * control/pid.ts - 1D and Pan-Tilt PID controllers with anti-windup and derivative filtering.
 * Faithful port of control/pid.py.
 */

import { PIDGains } from '../types/contracts';

export const DEFAULT_KP = 0.0003;
export const DEFAULT_KI = 0.00005;
export const DEFAULT_KD = 0.00002;
export const DEFAULT_MAX_OUTPUT_STEP = 0.003; // rad/step slew-rate limit (~3.8 px/step)
export const DERIVATIVE_ALPHA = 0.25; // Low-pass filter for derivative to suppress kick

export class PID1D {
  private kp: number;
  private ki: number;
  private kd: number;
  private maxStep: number;
  private integral: number = 0;
  private prevError: number | null = null;
  private filteredDerivative: number = 0;
  private integralLimit: number = 0.05;

  constructor(kp = DEFAULT_KP, ki = DEFAULT_KI, kd = DEFAULT_KD, maxStep = DEFAULT_MAX_OUTPUT_STEP) {
    this.kp = kp;
    this.ki = ki;
    this.kd = kd;
    this.maxStep = maxStep;
  }

  public setGains(gains: Partial<PIDGains>): void {
    if (gains.kp !== undefined) this.kp = gains.kp;
    if (gains.ki !== undefined) this.ki = gains.ki;
    if (gains.kd !== undefined) this.kd = gains.kd;
    if (gains.max_output_step !== undefined) this.maxStep = gains.max_output_step;
  }

  public reset(): void {
    this.integral = 0;
    this.prevError = null;
    this.filteredDerivative = 0;
  }

  public update(error: number, dt: number, isClamped: boolean = false): number {
    if (dt <= 0) return 0;

    // Proportional term
    const pTerm = this.kp * error;

    // Integral term with anti-windup: do not accumulate if joint was clamped in direction of error
    if (!isClamped) {
      this.integral += error * dt;
      this.integral = Math.max(-this.integralLimit, Math.min(this.integralLimit, this.integral));
    }
    const iTerm = this.ki * this.integral;

    // Derivative term with low-pass filtering
    let dTerm = 0;
    if (this.prevError !== null) {
      const rawD = (error - this.prevError) / dt;
      this.filteredDerivative = DERIVATIVE_ALPHA * rawD + (1 - DERIVATIVE_ALPHA) * this.filteredDerivative;
      dTerm = this.kd * this.filteredDerivative;
    }
    this.prevError = error;

    const rawOutput = pTerm + iTerm + dTerm;

    // Slew-rate limiting per timestep
    return Math.max(-this.maxStep, Math.min(this.maxStep, rawOutput));
  }
}

export class PanTiltPID {
  private panPID: PID1D;
  private tiltPID: PID1D;

  constructor(gains?: PIDGains) {
    const kp = gains?.kp ?? DEFAULT_KP;
    const ki = gains?.ki ?? DEFAULT_KI;
    const kd = gains?.kd ?? DEFAULT_KD;
    const maxStep = gains?.max_output_step ?? DEFAULT_MAX_OUTPUT_STEP;

    this.panPID = new PID1D(kp, ki, kd, maxStep);
    this.tiltPID = new PID1D(kp, ki, kd, maxStep);
  }

  public setGains(gains: PIDGains): void {
    this.panPID.setGains(gains);
    this.tiltPID.setGains(gains);
  }

  public reset(): void {
    this.panPID.reset();
    this.tiltPID.reset();
  }

  /**
   * Update PID:
   * Pan delta = +PID(error_x)
   * Tilt delta = -PID(error_y) (because image row y increases downward while elevation increases upward)
   */
  public update(
    errorPx: [number, number],
    dt: number,
    panClamped: boolean = false,
    tiltClamped: boolean = false
  ): [number, number] {
    const deltaPan = this.panPID.update(errorPx[0], dt, panClamped);
    const deltaTilt = -this.tiltPID.update(errorPx[1], dt, tiltClamped);
    return [deltaPan, deltaTilt];
  }
}
