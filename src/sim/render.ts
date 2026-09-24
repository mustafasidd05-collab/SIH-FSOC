/**
 * sim/render.ts - Rasterizer producing virtual camera frames with realistic point spread function (PSF).
 * Faithful port of sim/render.py.
 */

import { CameraState, TargetState } from '../types/contracts';
import { boresightAzEl, projectAzEl, isVisible } from './camera';
import { DisturbancePipeline } from '../disturbance/pipeline';

export class SceneRenderer {
  /**
   * Render targets and disturbances directly to an HTML5 canvas 2D context.
   */
  public renderToCanvas(
    ctx: CanvasRenderingContext2D,
    targets: TargetState[],
    camera: CameraState,
    t: number,
    dt: number,
    disturbance: DisturbancePipeline
  ): { targetPixelCoords: Array<{ targetId: number; px: number; py: number; visible: boolean; role?: string }> } {
    const width = camera.width_px;
    const height = camera.height_px;

    // 1. Draw near-black background with subtle sensor baseline (RGB 8, 9, 12)
    ctx.fillStyle = '#08090C';
    ctx.fillRect(0, 0, width, height);

    // 2. Draw subtle sensor dark noise specks if enabled
    const noiseSigma = disturbance.getSensorNoiseSigma();
    if (noiseSigma > 0.5) {
      const numSpecks = Math.floor(noiseSigma * 25);
      ctx.fillStyle = 'rgba(180, 200, 220, 0.12)';
      for (let i = 0; i < numSpecks; i++) {
        const nx = Math.random() * width;
        const ny = Math.random() * height;
        ctx.fillRect(nx, ny, 1, 1);
      }
    }

    // 3. Compute disturbances
    const [vibX, vibY] = disturbance.getVibrationOffset(dt);
    const { radiusPx, scintillation } = disturbance.getTurbulenceEffects(t);
    const transmission = disturbance.getTransmission(t);

    const projectedTargets: Array<{ targetId: number; px: number; py: number; visible: boolean; role?: string }> = [];

    // 4. Render each target as a Gaussian PSF blob
    for (const target of targets) {
      const visibleInFov = isVisible(target, camera);
      if (!visibleInFov) {
        projectedTargets.push({ targetId: target.target_id, px: -999, py: -999, visible: false, role: target.role });
        continue;
      }

      const [azRel, elRel] = boresightAzEl(target.az_rad, target.el_rad, camera.pan_rad, camera.tilt_rad);
      const [nominalPx, nominalPy] = projectAzEl(azRel, elRel, camera);

      // Add vibration jitter to image plane
      const px = nominalPx + vibX;
      const py = nominalPy + vibY;

      // Inside sensor boundary?
      const inFrame = px >= 0 && px < width && py >= 0 && py < height;
      projectedTargets.push({ targetId: target.target_id, px, py, visible: inFrame, role: target.role });

      if (!inFrame) continue;

      // Calculate effective beacon intensity
      const effectiveIntensity = Math.min(1.0, scintillation * transmission);
      if (effectiveIntensity < 0.05) continue; // Completely occluded by cloud

      // Distractor might be dimmer or different color
      const isDistractor = target.role === 'distractor';
      const intensity = isDistractor ? effectiveIntensity * 0.75 : effectiveIntensity;
      const spotRadius = isDistractor ? radiusPx * 0.85 : radiusPx;

      // Additive Gaussian point spread function rendering
      const grad = ctx.createRadialGradient(px, py, 0, px, py, spotRadius * 2.5);
      const alphaCore = Math.min(1.0, intensity);
      const alphaHalo = alphaCore * 0.35;

      if (isDistractor) {
        grad.addColorStop(0, `rgba(255, 230, 200, ${alphaCore})`);
        grad.addColorStop(0.3, `rgba(240, 210, 180, ${alphaHalo})`);
        grad.addColorStop(1, 'rgba(240, 210, 180, 0)');
      } else {
        grad.addColorStop(0, `rgba(245, 250, 255, ${alphaCore})`);
        grad.addColorStop(0.25, `rgba(225, 240, 255, ${alphaHalo})`);
        grad.addColorStop(1, 'rgba(200, 230, 255, 0)');
      }

      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(px, py, spotRadius * 2.5, 0, 2 * Math.PI);
      ctx.fill();

      // Sharp central diffraction spot
      ctx.fillStyle = isDistractor
        ? `rgba(255, 245, 230, ${alphaCore})`
        : `rgba(255, 255, 255, ${alphaCore})`;
      ctx.beginPath();
      ctx.arc(px, py, Math.max(1.0, spotRadius * 0.4), 0, 2 * Math.PI);
      ctx.fill();
      ctx.restore();
    }

    return { targetPixelCoords: projectedTargets };
  }
}
