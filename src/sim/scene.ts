/**
 * sim/scene.ts - Scene model, analytical target trajectories, and beacon management.
 * Faithful port of sim/scene.py.
 */

import { TargetState, SceneConfig } from '../types/contracts';

export class Scene {
  private config: SceneConfig;
  private distractorSeeds: Array<{ az0: number; el0: number; freq: number; phase: number }>;

  constructor(config: SceneConfig) {
    this.config = config;
    this.distractorSeeds = [
      { az0: 0.012, el0: -0.008, freq: 0.4, phase: 1.2 },
      { az0: -0.015, el0: 0.010, freq: 0.25, phase: 2.8 },
    ];
  }

  public updateConfig(config: SceneConfig): void {
    this.config = config;
  }

  /**
   * Evaluate ground-truth target states analytically at time t (seconds).
   */
  public getTargets(t: number): TargetState[] {
    const targets: TargetState[] = [];
    const speedFactor = this.config.target_speed_mps / 15.0; // Normalized to 15 m/s base

    let primaryAz = 0;
    let primaryEl = 0;

    switch (this.config.motion_pattern) {
      case 'linear': {
        const azRate = 0.004 * speedFactor;
        const elRate = 0.002 * speedFactor;
        // Bounce back and forth smoothly within +/- 0.03 rad (~1.7 deg)
        const cycle = 12.0 / speedFactor;
        const phase = (t % cycle) / cycle;
        const triangleWave = Math.abs(2 * (phase - Math.floor(phase + 0.5)));
        primaryAz = (triangleWave - 0.5) * 0.04;
        primaryEl = Math.sin(t * 0.5 * speedFactor) * 0.015;
        break;
      }
      case 'sinusoidal': {
        const freq = 0.3 * speedFactor;
        const ampAz = 0.025;
        const ampEl = 0.018;
        primaryAz = ampAz * Math.sin(2 * Math.PI * freq * t);
        primaryEl = ampEl * Math.sin(2 * Math.PI * freq * 0.7 * t + Math.PI / 4);
        break;
      }
      case 'lissajous': {
        // Lissajous curve with 3:2 frequency ratio
        const freq = 0.25 * speedFactor;
        const ampAz = 0.024;
        const ampEl = 0.016;
        primaryAz = ampAz * Math.sin(2 * Math.PI * freq * 3 * t);
        primaryEl = ampEl * Math.sin(2 * Math.PI * freq * 2 * t + Math.PI / 3);
        break;
      }
      case 'spiral': {
        // Spiral track: oscillating radius with slow rotation
        const freq = 0.35 * speedFactor;
        const radius = 0.01 + 0.015 * Math.abs(Math.sin(t * 0.1));
        primaryAz = radius * Math.cos(2 * Math.PI * freq * t);
        primaryEl = radius * Math.sin(2 * Math.PI * freq * t);
        break;
      }
    }

    // Convert az/el to world unit vector at 1000m range
    const range = 1000.0;
    const cosEl = Math.cos(primaryEl);
    targets.push({
      target_id: 1,
      world_pos: [
        range * cosEl * Math.sin(primaryAz),
        range * Math.sin(primaryEl),
        range * cosEl * Math.cos(primaryAz),
      ],
      az_rad: primaryAz,
      el_rad: primaryEl,
      range_m: range,
      visible: true,
      role: 'primary',
    });

    // Add distractors if enabled
    if (this.config.enable_distractors) {
      this.distractorSeeds.forEach((seed, index) => {
        const dAz = seed.az0 + 0.008 * Math.sin(2 * Math.PI * seed.freq * speedFactor * t + seed.phase);
        const dEl = seed.el0 + 0.006 * Math.cos(2 * Math.PI * seed.freq * speedFactor * t + seed.phase);
        const dCosEl = Math.cos(dEl);
        targets.push({
          target_id: index + 2,
          world_pos: [
            range * dCosEl * Math.sin(dAz),
            range * Math.sin(dEl),
            range * dCosEl * Math.cos(dAz),
          ],
          az_rad: dAz,
          el_rad: dEl,
          range_m: range,
          visible: true,
          role: 'distractor',
        });
      });
    }

    return targets;
  }
}
