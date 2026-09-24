/**
 * control/loop.ts - Closed-loop orchestrator tying TrackResult -> PID -> sim.camera.commandPanTilt.
 * Faithful port of control/loop.py.
 */

import { CameraState, TrackResult, TrackState, PIDGains } from '../types/contracts';
import { PanTiltPID } from './pid';
import { commandPanTilt, ClampReport } from '../sim/camera';

export class ControlLoop {
  private pid: PanTiltPID;
  private lastClampReport: ClampReport = { pan_clamped: false, tilt_clamped: false };

  constructor(gains?: PIDGains) {
    this.pid = new PanTiltPID(gains);
  }

  public setGains(gains: PIDGains): void {
    this.pid.setGains(gains);
  }

  public reset(): void {
    this.pid.reset();
    this.lastClampReport = { pan_clamped: false, tilt_clamped: false };
  }

  public step(
    trackResult: TrackResult,
    camera: CameraState,
    dt: number
  ): { camera: CameraState; clampReport: ClampReport } {
    // Only close loop when tracker has acquired or reacquired lock
    const isActive =
      trackResult.state === TrackState.TRACK ||
      trackResult.state === TrackState.REACQUIRE;

    if (!isActive || isNaN(trackResult.error_px[0]) || isNaN(trackResult.error_px[1])) {
      this.pid.reset();
      this.lastClampReport = { pan_clamped: false, tilt_clamped: false };
      return { camera, clampReport: this.lastClampReport };
    }

    const [deltaPan, deltaTilt] = this.pid.update(
      trackResult.error_px,
      dt,
      this.lastClampReport.pan_clamped,
      this.lastClampReport.tilt_clamped
    );

    const [updatedCamera, clampReport] = commandPanTilt(
      camera,
      camera.pan_rad + deltaPan,
      camera.tilt_rad + deltaTilt
    );

    this.lastClampReport = clampReport;
    return { camera: updatedCamera, clampReport };
  }
}
