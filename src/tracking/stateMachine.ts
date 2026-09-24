/**
 * tracking/stateMachine.ts - Tracking state machine.
 * Faithful port of tracking/state_machine.py.
 *
 * SEARCH -> ACQUIRE -> TRACK -> LOST -> REACQUIRE -> TRACK
 */

import { Detection, TrackResult, TrackState } from '../types/contracts';
import { KalmanTracker } from './kalman';

// Named thresholds matching tracking/state_machine.py exactly
export const CONFIDENCE_TO_ACQUIRE = 0.6;
export const FRAMES_TO_ACQUIRE = 3;
export const CONFIDENCE_TO_CONFIRM_TRACK = 0.5;
export const FRAMES_TO_CONFIRM = 3;
export const MISSES_TO_ABORT_ACQUIRE = 3;

export const TRACK_CONFIDENCE_MIN = 0.45;
export const MAX_MISSES_BEFORE_LOST = 10;
export const GATE_RADIUS_PX = 80.0;

export const REACQUIRE_CONFIDENCE = 0.55;
export const FRAMES_TO_REACQUIRE = 3;
export const MISSES_TO_ABORT_REACQUIRE = 3;
export const LOST_TIMEOUT_FRAMES = 180;

export class TrackStateMachine {
  private kalman: KalmanTracker;
  private state: TrackState = TrackState.SEARCH;

  private acquireCount: number = 0;
  private confirmCount: number = 0;
  private reacquireCount: number = 0;
  private missCount: number = 0;
  private lostFrameCount: number = 0;

  constructor(kalman: KalmanTracker) {
    this.kalman = kalman;
  }

  public get currentState(): TrackState {
    return this.state;
  }

  public get gateRadiusPx(): number {
    return GATE_RADIUS_PX;
  }

  public reset(): void {
    this.state = TrackState.SEARCH;
    this.acquireCount = 0;
    this.confirmCount = 0;
    this.reacquireCount = 0;
    this.missCount = 0;
    this.lostFrameCount = 0;
    this.kalman.reset();
  }

  /**
   * Advance state machine by one frame.
   */
  public step(
    detection: Detection | null,
    dt: number,
    frameId: number,
    timestampS: number,
    centerPx: [number, number]
  ): TrackResult {
    // 1. Advance Kalman prediction
    const prediction = this.kalman.isActive ? this.kalman.predict(dt) : null;

    // 2. Validate detection against state confidence and gate
    let acceptedDetection: Detection | null = null;
    if (detection !== null) {
      if (prediction !== null) {
        const dist = Math.hypot(
          detection.centroid_px[0] - prediction[0],
          detection.centroid_px[1] - prediction[1]
        );
        if (dist <= GATE_RADIUS_PX) {
          acceptedDetection = detection;
        }
      } else {
        acceptedDetection = detection;
      }
    }

    // 3. State transition logic
    switch (this.state) {
      case TrackState.SEARCH: {
        if (acceptedDetection && acceptedDetection.confidence >= CONFIDENCE_TO_ACQUIRE) {
          this.acquireCount += 1;
          if (this.acquireCount >= FRAMES_TO_ACQUIRE) {
            this.kalman.seed(acceptedDetection.centroid_px);
            this.state = TrackState.ACQUIRE;
            this.confirmCount = 0;
            this.missCount = 0;
          }
        } else {
          this.acquireCount = 0;
        }
        break;
      }

      case TrackState.ACQUIRE: {
        if (acceptedDetection && acceptedDetection.confidence >= CONFIDENCE_TO_CONFIRM_TRACK) {
          this.kalman.update(acceptedDetection.centroid_px);
          this.confirmCount += 1;
          this.missCount = 0;
          if (this.confirmCount >= FRAMES_TO_CONFIRM) {
            this.state = TrackState.TRACK;
            this.missCount = 0;
          }
        } else {
          this.missCount += 1;
          if (this.missCount >= MISSES_TO_ABORT_ACQUIRE) {
            this.reset();
          }
        }
        break;
      }

      case TrackState.TRACK: {
        if (acceptedDetection && acceptedDetection.confidence >= TRACK_CONFIDENCE_MIN) {
          this.kalman.update(acceptedDetection.centroid_px);
          this.missCount = 0;
        } else {
          this.missCount += 1;
          if (this.missCount >= MAX_MISSES_BEFORE_LOST) {
            this.state = TrackState.LOST;
            this.lostFrameCount = 0;
            this.reacquireCount = 0;
          }
        }
        break;
      }

      case TrackState.LOST: {
        this.lostFrameCount += 1;
        if (this.lostFrameCount >= LOST_TIMEOUT_FRAMES) {
          this.reset();
        } else if (acceptedDetection && acceptedDetection.confidence >= REACQUIRE_CONFIDENCE) {
          this.reacquireCount += 1;
          if (this.reacquireCount >= FRAMES_TO_REACQUIRE) {
            this.kalman.update(acceptedDetection.centroid_px);
            this.state = TrackState.REACQUIRE;
            this.confirmCount = 0;
            this.missCount = 0;
          }
        } else {
          this.reacquireCount = 0;
        }
        break;
      }

      case TrackState.REACQUIRE: {
        if (acceptedDetection && acceptedDetection.confidence >= CONFIDENCE_TO_CONFIRM_TRACK) {
          this.kalman.update(acceptedDetection.centroid_px);
          this.confirmCount += 1;
          this.missCount = 0;
          if (this.confirmCount >= FRAMES_TO_CONFIRM) {
            this.state = TrackState.TRACK;
            this.missCount = 0;
          }
        } else {
          this.missCount += 1;
          if (this.missCount >= MISSES_TO_ABORT_REACQUIRE) {
            this.state = TrackState.LOST;
          }
        }
        break;
      }
    }

    // 4. Construct TrackResult
    // Error is defined as (centroid_x - W/2, centroid_y - H/2)
    // Per contract: in non-TRACK states, error_px is NaN/NaN
    let centroidPx: [number, number] = [0, 0];
    let bboxPx: [number, number, number, number] = [0, 0, 0, 0];
    let confidence = 0;
    let errorPx: [number, number] = [NaN, NaN];

    const currentMean = this.kalman.meanPx;
    if (this.state === TrackState.TRACK && currentMean) {
      centroidPx = currentMean;
      bboxPx = [currentMean[0] - 12, currentMean[1] - 12, 24, 24];
      confidence = acceptedDetection ? acceptedDetection.confidence : 0.8;
      errorPx = [currentMean[0] - centerPx[0], currentMean[1] - centerPx[1]];
    } else if (acceptedDetection) {
      centroidPx = acceptedDetection.centroid_px;
      bboxPx = acceptedDetection.bbox_px;
      confidence = acceptedDetection.confidence;
      if (this.state === TrackState.ACQUIRE || this.state === TrackState.REACQUIRE) {
        errorPx = [centroidPx[0] - centerPx[0], centroidPx[1] - centerPx[1]];
      }
    }

    return {
      frame_id: frameId,
      timestamp_s: timestampS,
      state: this.state,
      centroid_px: centroidPx,
      bbox_px: bboxPx,
      confidence,
      error_px: errorPx,
    };
  }
}
