/**
 * telemetry/performanceLogger.ts - Aggregation, metric calculation, and JSON performance log export/import.
 * Faithful port of telemetry/performance_logger.py.
 */

import { PerformanceSummary, TelemetryPacket, TrackState } from '../types/contracts';

export class PerformanceLogger {
  private packets: TelemetryPacket[] = [];
  private startTimeS: number | null = null;
  private firstSearchTimeS: number | null = null;
  private acquisitionTimeS: number | null = null;

  public reset(): void {
    this.packets = [];
    this.startTimeS = null;
    this.firstSearchTimeS = null;
    this.acquisitionTimeS = null;
  }

  public logPacket(packet: TelemetryPacket): void {
    this.packets.push(packet);

    if (this.startTimeS === null) {
      this.startTimeS = packet.timestamp_s;
    }

    if (packet.track_state === TrackState.SEARCH && this.firstSearchTimeS === null) {
      this.firstSearchTimeS = packet.timestamp_s;
    }

    if (packet.track_state === TrackState.TRACK && this.acquisitionTimeS === null) {
      const baseTime = this.firstSearchTimeS !== null ? this.firstSearchTimeS : this.startTimeS;
      this.acquisitionTimeS = Math.max(0, packet.timestamp_s - baseTime);
    }
  }

  public getPackets(): TelemetryPacket[] {
    return this.packets;
  }

  public getAcquisitionTime(): number {
    return this.acquisitionTimeS !== null ? this.acquisitionTimeS : NaN;
  }

  public getLockRetentionRate(windowSize: number = 60): number {
    if (this.packets.length === 0) return 0;
    const slice = this.packets.slice(-windowSize);
    const lockedFrames = slice.filter(
      (p) => p.track_state === TrackState.TRACK || p.track_state === TrackState.REACQUIRE
    ).length;
    return lockedFrames / slice.length;
  }

  public getSummary(): PerformanceSummary {
    const totalFrames = this.packets.length;
    if (totalFrames === 0) {
      return {
        total_frames: 0,
        duration_s: 0,
        average_fps: 0,
        acquisition_time_s: NaN,
        lock_retention_rate: 0,
        mean_error_px: 0,
        rmse_error_px: 0,
        max_error_px: 0,
      };
    }

    const duration =
      this.packets[totalFrames - 1].timestamp_s - this.packets[0].timestamp_s;
    const avgFps = duration > 0 ? (totalFrames - 1) / duration : 0;

    let trackedCount = 0;
    let sumErr = 0;
    let sumSqErr = 0;
    let maxErr = 0;

    let lockedCount = 0;

    for (const p of this.packets) {
      if (p.track_state === TrackState.TRACK || p.track_state === TrackState.REACQUIRE) {
        lockedCount++;
      }

      if (p.track_state === TrackState.TRACK && !isNaN(p.error_px[0]) && !isNaN(p.error_px[1])) {
        const err = Math.hypot(p.error_px[0], p.error_px[1]);
        sumErr += err;
        sumSqErr += err * err;
        if (err > maxErr) maxErr = err;
        trackedCount++;
      }
    }

    const meanErr = trackedCount > 0 ? sumErr / trackedCount : 0;
    const rmseErr = trackedCount > 0 ? Math.sqrt(sumSqErr / trackedCount) : 0;
    const lockRetention = totalFrames > 0 ? lockedCount / totalFrames : 0;

    return {
      total_frames: totalFrames,
      duration_s: duration,
      average_fps: avgFps,
      acquisition_time_s: this.acquisitionTimeS !== null ? this.acquisitionTimeS : NaN,
      lock_retention_rate: lockRetention,
      mean_error_px: meanErr,
      rmse_error_px: rmseErr,
      max_error_px: maxErr,
    };
  }

  public exportJSON(): string {
    const summary = this.getSummary();
    const payload = {
      summary,
      packets: this.packets.map((p) => ({
        frame_id: p.frame_id,
        timestamp_s: p.timestamp_s,
        fps: p.fps,
        track_state: p.track_state,
        error_px: p.error_px,
        error_az_rad: p.error_az_rad,
        error_el_rad: p.error_el_rad,
        lock_fraction: p.lock_fraction,
        acquisition_time_s: p.acquisition_time_s,
        loop_time_s: p.loop_time_s,
      })),
    };
    return JSON.stringify(payload, null, 2);
  }
}
