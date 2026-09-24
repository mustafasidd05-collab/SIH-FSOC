/**
 * tracking/kalman.ts - 4-state constant-velocity Kalman filter for target tracking.
 * Faithful port of tracking/kalman.py.
 */

export const DT_MIN_S = 1.0 / 60.0;
export const PROCESS_NOISE_VAR = 2000.0;
export const MEASUREMENT_NOISE_VAR = 4.0;

export class KalmanTracker {
  private x: [number, number, number, number] | null = null; // [x, y, vx, vy]
  private P: number[][] = []; // 4x4 covariance matrix
  private q: number;
  private r: number;

  constructor(q: number = PROCESS_NOISE_VAR, r: number = MEASUREMENT_NOISE_VAR) {
    this.q = q;
    this.r = r;
    this.reset();
  }

  public get isActive(): boolean {
    return this.x !== null;
  }

  public get meanPx(): [number, number] | null {
    if (!this.x) return null;
    return [this.x[0], this.x[1]];
  }

  public get velocityPxS(): [number, number] | null {
    if (!this.x) return null;
    return [this.x[2], this.x[3]];
  }

  public reset(): void {
    this.x = null;
    this.P = [
      [100, 0, 0, 0],
      [0, 100, 0, 0],
      [0, 0, 500, 0],
      [0, 0, 0, 500],
    ];
  }

  public seed(centroidPx: [number, number]): void {
    this.x = [centroidPx[0], centroidPx[1], 0, 0];
    this.P = [
      [this.r, 0, 0, 0],
      [0, this.r, 0, 0],
      [0, 0, 500, 0],
      [0, 0, 0, 500],
    ];
  }

  /**
   * Kalman prediction step with timestep dt.
   */
  public predict(dt: number): [number, number] | null {
    if (!this.x) return null;
    const clampedDt = Math.max(DT_MIN_S, dt);

    // State extrapolation: x_k = x_{k-1} + vx * dt
    this.x[0] += this.x[2] * clampedDt;
    this.x[1] += this.x[3] * clampedDt;

    // Process noise integration
    const dt2 = (clampedDt * clampedDt) / 2.0;
    const dt3 = (clampedDt * clampedDt * clampedDt) / 3.0;

    // Update covariance P = F * P * F^T + Q
    this.P[0][0] += 2 * clampedDt * this.P[2][0] + clampedDt * clampedDt * this.P[2][2] + dt3 * this.q;
    this.P[1][1] += 2 * clampedDt * this.P[3][1] + clampedDt * clampedDt * this.P[3][3] + dt3 * this.q;
    this.P[2][2] += clampedDt * this.q;
    this.P[3][3] += clampedDt * this.q;
    this.P[0][2] += clampedDt * this.P[2][2] + dt2 * this.q;
    this.P[2][0] = this.P[0][2];
    this.P[1][3] += clampedDt * this.P[3][3] + dt2 * this.q;
    this.P[3][1] = this.P[1][3];

    return [this.x[0], this.x[1]];
  }

  /**
   * Kalman measurement update step with detected centroid.
   */
  public update(measurementPx: [number, number]): [number, number] {
    if (!this.x) {
      this.seed(measurementPx);
      return measurementPx;
    }

    // Residual (innovation)
    const y0 = measurementPx[0] - this.x[0];
    const y1 = measurementPx[1] - this.x[1];

    // Innovation covariance S = H * P * H^T + R
    const s00 = this.P[0][0] + this.r;
    const s11 = this.P[1][1] + this.r;

    // Kalman gain K = P * H^T * S^-1
    const k0 = this.P[0][0] / s00;
    const k1 = this.P[1][1] / s11;
    const k2 = this.P[2][0] / s00;
    const k3 = this.P[3][1] / s11;

    // State update
    this.x[0] += k0 * y0;
    this.x[1] += k1 * y1;
    this.x[2] += k2 * y0;
    this.x[3] += k3 * y1;

    // Covariance update: P = (I - K*H) * P
    this.P[0][0] *= 1.0 - k0;
    this.P[1][1] *= 1.0 - k1;
    this.P[2][0] *= 1.0 - k0;
    this.P[3][1] *= 1.0 - k1;
    this.P[0][2] = this.P[2][0];
    this.P[1][3] = this.P[3][1];

    return [this.x[0], this.x[1]];
  }
}
