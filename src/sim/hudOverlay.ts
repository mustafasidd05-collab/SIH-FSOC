/**
 * sim/hudOverlay.ts - Draws QPainter-faithful HUD overlays directly on the canvas context.
 * Faithful port of ui/overlay.py.
 */

import { TrackResult, TrackState, STATE_COLORS } from '../types/contracts';

export function drawHudOverlay(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  trackResult: TrackResult | null
): void {
  const boresightX = width / 2.0;
  const boresightY = height / 2.0;

  const state = trackResult?.state ?? TrackState.SEARCH;
  const accentColor = STATE_COLORS[state];

  ctx.save();

  // 1. Draw Boresight Center Reticle
  ctx.strokeStyle = accentColor;
  ctx.lineWidth = 1.25;

  const reticleGap = 6;
  const reticleArm = 18;
  const tickLen = 5;

  // Horizontal arms with gap
  ctx.beginPath();
  ctx.moveTo(boresightX - reticleGap - reticleArm, boresightY);
  ctx.lineTo(boresightX - reticleGap, boresightY);
  ctx.moveTo(boresightX + reticleGap, boresightY);
  ctx.lineTo(boresightX + reticleGap + reticleArm, boresightY);

  // Vertical arms with gap
  ctx.moveTo(boresightX, boresightY - reticleGap - reticleArm);
  ctx.lineTo(boresightX, boresightY - reticleGap);
  ctx.moveTo(boresightX, boresightY + reticleGap);
  ctx.lineTo(boresightX, boresightY + reticleGap + reticleArm);

  // Cross ticks
  ctx.moveTo(boresightX - reticleGap - reticleArm, boresightY - tickLen);
  ctx.lineTo(boresightX - reticleGap - reticleArm, boresightY + tickLen);
  ctx.moveTo(boresightX + reticleGap + reticleArm, boresightY - tickLen);
  ctx.lineTo(boresightX + reticleGap + reticleArm, boresightY + tickLen);

  ctx.moveTo(boresightX - tickLen, boresightY - reticleGap - reticleArm);
  ctx.lineTo(boresightX + tickLen, boresightY - reticleGap - reticleArm);
  ctx.moveTo(boresightX - tickLen, boresightY + reticleGap + reticleArm);
  ctx.lineTo(boresightX + tickLen, boresightY + reticleGap + reticleArm);
  ctx.stroke();

  // Boresight tiny center dot
  ctx.fillStyle = accentColor;
  ctx.beginPath();
  ctx.arc(boresightX, boresightY, 1.5, 0, 2 * Math.PI);
  ctx.fill();

  // 2. Target Centroid, Bounding Box, and Error Vector
  if (trackResult && state !== TrackState.LOST && !isNaN(trackResult.error_px[0]) && !isNaN(trackResult.error_px[1])) {
    const errX = trackResult.error_px[0];
    const errY = trackResult.error_px[1];
    const targetX = boresightX + errX;
    const targetY = boresightY + errY;

    // Dashed line from boresight to target centroid
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = accentColor;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    ctx.moveTo(boresightX, boresightY);
    ctx.lineTo(targetX, targetY);
    ctx.stroke();
    ctx.setLineDash([]); // Reset line dash

    // Error distance label at midpoint
    const errDist = Math.hypot(errX, errY);
    const midX = (boresightX + targetX) / 2.0;
    const midY = (boresightY + targetY) / 2.0;

    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.fillStyle = accentColor;
    ctx.fillText(`${errDist.toFixed(1)}px`, midX + 6, midY - 4);

    // Bounding box size: 24px in TRACK, 38px in others
    const boxSize = state === TrackState.TRACK ? 24.0 : 38.0;
    const halfBox = boxSize / 2.0;
    const boxLeft = targetX - halfBox;
    const boxTop = targetY - halfBox;

    // Bounding box outline
    ctx.strokeStyle = accentColor;
    ctx.lineWidth = 1.25;
    ctx.strokeRect(boxLeft, boxTop, boxSize, boxSize);

    // Corner brackets
    const cornerLen = 6.0;
    ctx.lineWidth = 2.0;
    ctx.beginPath();
    // Top-Left
    ctx.moveTo(boxLeft, boxTop + cornerLen);
    ctx.lineTo(boxLeft, boxTop);
    ctx.lineTo(boxLeft + cornerLen, boxTop);
    // Top-Right
    ctx.moveTo(boxLeft + boxSize - cornerLen, boxTop);
    ctx.lineTo(boxLeft + boxSize, boxTop);
    ctx.lineTo(boxLeft + boxSize, boxTop + cornerLen);
    // Bottom-Left
    ctx.moveTo(boxLeft, boxTop + boxSize - cornerLen);
    ctx.lineTo(boxLeft, boxTop + boxSize);
    ctx.lineTo(boxLeft + cornerLen, boxTop + boxSize);
    // Bottom-Right
    ctx.moveTo(boxLeft + boxSize - cornerLen, boxTop + boxSize);
    ctx.lineTo(boxLeft + boxSize, boxTop + boxSize);
    ctx.lineTo(boxLeft + boxSize, boxTop + boxSize - cornerLen);
    ctx.stroke();

    // Target centroid cross + dot
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    ctx.moveTo(targetX - 5, targetY);
    ctx.lineTo(targetX + 5, targetY);
    ctx.moveTo(targetX, targetY - 5);
    ctx.lineTo(targetX, targetY + 5);
    ctx.stroke();

    ctx.fillStyle = accentColor;
    ctx.beginPath();
    ctx.arc(targetX, targetY, 2.5, 0, 2 * Math.PI);
    ctx.fill();
  }

  ctx.restore();
}
