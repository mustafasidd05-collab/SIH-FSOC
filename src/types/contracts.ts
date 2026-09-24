/**
 * contracts.ts - Source of truth for every data shape crossing module boundaries.
 * Mirrors core/contracts.py and ui/palette.py exactly.
 *
 * Units convention:
 * - angles: radians
 * - lengths/distances: meters
 * - time: seconds
 * - pixel coordinates: integer/float pixels, origin top-left
 */

export enum TrackState {
  SEARCH = 'SEARCH',
  ACQUIRE = 'ACQUIRE',
  TRACK = 'TRACK',
  LOST = 'LOST',
  REACQUIRE = 'REACQUIRE',
}

export const STATE_COLORS: Record<TrackState, string> = {
  [TrackState.SEARCH]: '#FFB300',    // Amber
  [TrackState.ACQUIRE]: '#39C5CF',   // Cyan
  [TrackState.TRACK]: '#00E676',     // Green
  [TrackState.LOST]: '#FF4D4F',      // Red
  [TrackState.REACQUIRE]: '#B57CFF', // Violet
};

export interface CameraState {
  pan_rad: number;
  tilt_rad: number;
  pan_min_rad: number;
  pan_max_rad: number;
  tilt_min_rad: number;
  tilt_max_rad: number;
  fov_h_rad: number;
  fov_v_rad: number;
  width_px: number;
  height_px: number;
}

export interface TargetState {
  target_id: number;
  world_pos: [number, number, number];
  az_rad: number;
  el_rad: number;
  range_m: number;
  visible: boolean;
  role?: 'primary' | 'distractor';
}

export interface SimFrame {
  frame_id: number;
  timestamp_s: number;
  image: ImageData | null;
  camera: CameraState;
}

export interface Detection {
  centroid_px: [number, number];
  bbox_px: [number, number, number, number]; // [x, y, w, h]
  confidence: number;
  peak_intensity: number;
  area_px: number;
}

export interface TrackResult {
  frame_id: number;
  timestamp_s: number;
  state: TrackState;
  centroid_px: [number, number];
  bbox_px: [number, number, number, number];
  confidence: number;
  error_px: [number, number]; // Boresight-relative: (centroid_x - W/2, centroid_y - H/2)
}

export interface TelemetryPacket {
  frame_id: number;
  timestamp_s: number;
  fps: number;
  track_state: TrackState;
  error_px: [number, number];
  error_az_rad: number;
  error_el_rad: number;
  lock_fraction: number;
  acquisition_time_s: number;
  loop_time_s: number;
}

export interface PerformanceSummary {
  total_frames: number;
  duration_s: number;
  average_fps: number;
  acquisition_time_s: number;
  lock_retention_rate: number;
  mean_error_px: number;
  rmse_error_px: number;
  max_error_px: number;
}

export interface DisturbanceConfig {
  profile: 'mild' | 'moderate' | 'severe' | 'custom';
  enable_turbulence: boolean;
  enable_vibration: boolean;
  enable_sensor_noise: boolean;
  enable_occlusion: boolean;
  enable_motion_blur: boolean;
  vibration_sigma_urad: number; // 0..50
  turbulence_index: number;     // 0..100
  sensor_noise_sigma: number;   // 0..20
}

export interface SceneConfig {
  target_speed_mps: number;     // 1..100
  motion_pattern: 'linear' | 'sinusoidal' | 'lissajous' | 'spiral';
  enable_distractors: boolean;
}

export interface PIDGains {
  kp: number;
  ki: number;
  kd: number;
  max_output_step: number;
}
