/**
 * tracking/pipeline.ts - High-level tracking pipeline coordinating detector, Kalman, and state machine.
 * Faithful port of tracking/pipeline.py.
 */

import { CameraState, Detection, SimFrame, TrackResult } from '../types/contracts';
import { BeaconDetector } from './detect';
import { KalmanTracker, DT_MIN_S } from './kalman';
import { TrackStateMachine } from './stateMachine';

export class TrackPipeline {
  private detector: BeaconDetector;
  private kalman: KalmanTracker;
  private stateMachine: TrackStateMachine;
  private lastTimestampS: number | null = null;
  private selectedTargetPx: [number, number] | null = null;

  constructor() {
    this.detector = new BeaconDetector();
    this.kalman = new KalmanTracker();
    this.stateMachine = new TrackStateMachine(this.kalman);
  }

  public get state(): TrackStateMachine {
    return this.stateMachine;
  }

  public selectTarget(centroidPx: [number, number]): void {
    this.stateMachine.reset();
    this.selectedTargetPx = [centroidPx[0], centroidPx[1]];
  }

  public reset(): void {
    this.stateMachine.reset();
    this.selectedTargetPx = null;
    this.lastTimestampS = null;
  }

  /**
   * Process one SimFrame: run detection -> filter -> state machine -> TrackResult.
   */
  public process(
    frame: SimFrame,
    projectedTargets?: Array<{ targetId: number; px: number; py: number; visible: boolean; role?: string }>
  ): TrackResult {
    let candidates: Detection[] = [];
    if (frame.image) {
      candidates = this.detector.detectCandidates(frame.image, projectedTargets);
    }

    const referencePx = this.kalman.meanPx || this.selectedTargetPx;
    const gateRadiusPx = this.stateMachine.gateRadiusPx;

    let bestDetection: Detection | null = null;

    if (referencePx && candidates.length > 0) {
      // Prioritize candidates within the gate around prediction
      const gated = candidates.filter((c) => {
        const dist = Math.hypot(c.centroid_px[0] - referencePx[0], c.centroid_px[1] - referencePx[1]);
        return dist <= gateRadiusPx;
      });

      if (gated.length > 0) {
        // Nearest gated candidate
        gated.sort(
          (a, b) =>
            Math.hypot(a.centroid_px[0] - referencePx[0], a.centroid_px[1] - referencePx[1]) -
            Math.hypot(b.centroid_px[0] - referencePx[0], b.centroid_px[1] - referencePx[1])
        );
        bestDetection = gated[0];
      }
    }

    if (!bestDetection && candidates.length > 0) {
      // Pick highest confidence candidate
      candidates.sort((a, b) => b.confidence - a.confidence);
      bestDetection = candidates[0];
    }

    if (bestDetection && this.selectedTargetPx) {
      this.selectedTargetPx = bestDetection.centroid_px;
    }
    if (this.kalman.isActive) {
      this.selectedTargetPx = null;
    }

    const dt = this.lastTimestampS === null ? DT_MIN_S : frame.timestamp_s - this.lastTimestampS;
    this.lastTimestampS = frame.timestamp_s;

    const centerPx: [number, number] = [frame.camera.width_px / 2.0, frame.camera.height_px / 2.0];

    return this.stateMachine.step(
      bestDetection,
      dt,
      frame.frame_id,
      frame.timestamp_s,
      centerPx
    );
  }
}
