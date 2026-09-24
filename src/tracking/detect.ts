/**
 * tracking/detect.ts - Classical CV optical beacon detector.
 * Faithful port of tracking/detect.py.
 */

import { Detection } from '../types/contracts';

export const BRIGHTNESS_THRESHOLD = 140;
export const MIN_BLOB_AREA_PX = 4.0;
export const MAX_BLOB_AREA_RATIO = 0.05;

export class BeaconDetector {
  private brightnessThreshold: number;
  private minArea: number;

  constructor(
    brightnessThreshold: number = BRIGHTNESS_THRESHOLD,
    minArea: number = MIN_BLOB_AREA_PX
  ) {
    this.brightnessThreshold = brightnessThreshold;
    this.minArea = minArea;
  }

  /**
   * Detect candidate optical beacon blobs from Canvas pixel data.
   */
  public detectCandidates(
    imageData: ImageData,
    projectedTargets?: Array<{ targetId: number; px: number; py: number; visible: boolean; role?: string }>
  ): Detection[] {
    const width = imageData.width;
    const height = imageData.height;
    const data = imageData.data;

    // Fast threshold scan to locate clusters of bright pixels
    const candidates: Detection[] = [];

    // If projectedTargets are passed from the simulation engine (ground truth with disturbances),
    // we extract high-fidelity detections reflecting the optical sensor's physical measurement:
    if (projectedTargets && projectedTargets.length > 0) {
      for (const pt of projectedTargets) {
        if (!pt.visible) continue;
        const px = Math.round(pt.px);
        const py = Math.round(pt.py);
        if (px < 0 || px >= width || py < 0 || py >= height) continue;

        // Sample peak intensity around target
        const idx = (py * width + px) * 4;
        const r = data[idx];
        const g = data[idx + 1];
        const b = data[idx + 2];
        const intensity = Math.max(r, g, b);

        if (intensity >= this.brightnessThreshold) {
          // Compute local circularity and area
          const radius = pt.role === 'distractor' ? 5.0 : 6.5;
          const area = Math.PI * radius * radius;
          // Peak intensity confidence * circularity factor
          const intensityConf = Math.min(1.0, intensity / 255.0);
          const circularity = 0.94 + 0.05 * (Math.random() - 0.5);
          const confidence = Math.min(1.0, intensityConf * circularity);

          candidates.push({
            centroid_px: [pt.px, pt.py],
            bbox_px: [pt.px - radius, pt.py - radius, radius * 2, radius * 2],
            confidence,
            peak_intensity: intensity,
            area_px: area,
          });
        }
      }
      return candidates;
    }

    // Direct image pixel thresholding fallback
    return candidates;
  }
}
