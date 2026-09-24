/**
 * disturbance/pipeline.ts - Atmospheric turbulence, platform vibration, sensor noise,
 * and cloud occlusion pipeline. Faithful port of disturbance/pipeline.py and individual models.
 */

import { DisturbanceConfig } from '../types/contracts';

export const DISTURBANCE_PROFILES: Record<
  'mild' | 'moderate' | 'severe',
  {
    vibration_sigma_urad: number;
    turbulence_index: number;
    sensor_noise_sigma: number;
  }
> = {
  mild: {
    vibration_sigma_urad: 4,
    turbulence_index: 10,
    sensor_noise_sigma: 1,
  },
  moderate: {
    vibration_sigma_urad: 15,
    turbulence_index: 35,
    sensor_noise_sigma: 3,
  },
  severe: {
    vibration_sigma_urad: 35,
    turbulence_index: 70,
    sensor_noise_sigma: 7,
  },
};

export class DisturbancePipeline {
  private config: DisturbanceConfig;
  private vibrationStateX: number = 0;
  private vibrationStateY: number = 0;
  private cloudPhase: number = 0;

  constructor(config: DisturbanceConfig) {
    this.config = config;
  }

  public updateConfig(config: DisturbanceConfig): void {
    this.config = config;
  }

  /**
   * Calculate platform vibration jitter offset (pixels) using Ornstein-Uhlenbeck colored noise.
   */
  public getVibrationOffset(dt: number): [number, number] {
    if (!this.config.enable_vibration) return [0, 0];

    // Convert micro-radians to pixel shift
    // e.g. 15 urad across a 4 deg (0.07 rad) FOV on 640px sensor ~ 0.14 - 1.5 px
    const sigmaPx = (this.config.vibration_sigma_urad / 10.0) * 0.8;
    const tau = 0.15; // correlation time constant
    const alpha = Math.exp(-dt / tau);
    const randX = (Math.random() - 0.5) * 2 * Math.sqrt(1 - alpha * alpha) * sigmaPx;
    const randY = (Math.random() - 0.5) * 2 * Math.sqrt(1 - alpha * alpha) * sigmaPx;

    this.vibrationStateX = alpha * this.vibrationStateX + randX;
    this.vibrationStateY = alpha * this.vibrationStateY + randY;

    return [this.vibrationStateX, this.vibrationStateY];
  }

  /**
   * Atmospheric turbulence modifier: returns beacon radius expansion (sigma) and scintillation factor.
   */
  public getTurbulenceEffects(t: number): { radiusPx: number; scintillation: number } {
    if (!this.config.enable_turbulence) {
      return { radiusPx: 4.5, scintillation: 1.0 };
    }

    // Turbulence increases spot size (seeing blur) and flickers brightness (scintillation)
    const turbFactor = this.config.turbulence_index / 50.0;
    const baseRadius = 4.0 + turbFactor * 4.0;

    // Temporal scintillation via multi-sine wave approximation
    const scintNoise =
      0.15 * Math.sin(2 * Math.PI * 4.3 * t) +
      0.10 * Math.sin(2 * Math.PI * 11.2 * t + 1.4) +
      0.08 * (Math.random() - 0.5);

    const scintillation = Math.max(0.1, Math.min(1.4, 1.0 + turbFactor * scintNoise));
    const radiusPx = baseRadius + (Math.random() - 0.5) * 0.4 * turbFactor;

    return { radiusPx, scintillation };
  }

  /**
   * Cloud occlusion factor [0..1] where 1.0 is full transmission, <0.2 causes beacon dropout.
   */
  public getTransmission(t: number): number {
    if (!this.config.enable_occlusion) return 1.0;

    // Simulated cloud drifting periodically across the optical path
    // Cloud covers the path every ~15 seconds for a ~3 second duration
    const cloudCycle = (t * 0.12) % (2 * Math.PI);
    // Gaussian dip around cycle peak
    const distToDip = Math.abs(cloudCycle - Math.PI);
    if (distToDip < 0.8) {
      const drop = 1.0 - Math.exp(-Math.pow(distToDip / 0.35, 2));
      return Math.max(0.05, 0.05 + 0.95 * drop);
    }
    return 1.0;
  }

  /**
   * Get sensor noise level.
   */
  public getSensorNoiseSigma(): number {
    if (!this.config.enable_sensor_noise) return 0.0;
    return this.config.sensor_noise_sigma;
  }
}
