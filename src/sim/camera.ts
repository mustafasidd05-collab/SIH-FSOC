/**
 * sim/camera.ts - Virtual pan-tilt camera optics, 3D coordinate transforms, and gnomonic projection.
 * Faithful port of sim/camera.py.
 */

import { CameraState, TargetState } from '../types/contracts';

export interface ClampReport {
  pan_clamped: boolean;
  tilt_clamped: boolean;
}

/**
 * Recover boresight-relative azimuth and elevation angles for an absolute az/el target
 * under current gimbal pan/tilt orientation.
 */
export function boresightAzEl(
  azAbsRad: number,
  elAbsRad: number,
  panRad: number,
  tiltRad: number
): [number, number] {
  const cosEl = Math.cos(elAbsRad);
  const sinEl = Math.sin(elAbsRad);
  const vWorldX = cosEl * Math.sin(azAbsRad);
  const vWorldY = sinEl;
  const vWorldZ = cosEl * Math.cos(azAbsRad);

  const cp = Math.cos(panRad);
  const sp = Math.sin(panRad);
  const ct = Math.cos(tiltRad);
  const st = Math.sin(tiltRad);

  // Rotate world vector by Ry(-pan)
  const vPanX = vWorldX * cp - vWorldZ * sp;
  const vPanY = vWorldY;
  const vPanZ = vWorldX * sp + vWorldZ * cp;

  // Rotate by Rx(tilt)
  const vCamX = vPanX;
  const vCamY = vPanY * ct - vPanZ * st;
  const vCamZ = vPanY * st + vPanZ * ct;

  const azRel = Math.atan2(vCamX, vCamZ);
  const elRel = Math.atan2(vCamY, Math.hypot(vCamX, vCamZ));

  return [azRel, elRel];
}

/**
 * Gnomonic (pinhole) projection from boresight-relative angles to sensor pixel coordinates.
 */
export function projectAzEl(
  azRelRad: number,
  elRelRad: number,
  camera: CameraState
): [number, number] {
  const fx = (camera.width_px / 2.0) / Math.tan(camera.fov_h_rad / 2.0);
  const fy = (camera.height_px / 2.0) / Math.tan(camera.fov_v_rad / 2.0);

  const px = camera.width_px / 2.0 + fx * Math.tan(azRelRad);
  const py = camera.height_px / 2.0 - fy * Math.tan(elRelRad);

  return [px, py];
}

/**
 * Check target visibility in camera field of view.
 */
export function isVisible(
  target: TargetState,
  camera: CameraState
): boolean {
  if (target.range_m <= 0) return false;
  const [azRel, elRel] = boresightAzEl(target.az_rad, target.el_rad, camera.pan_rad, camera.tilt_rad);
  return (
    Math.abs(azRel) <= camera.fov_h_rad / 2.0 &&
    Math.abs(elRel) <= camera.fov_v_rad / 2.0
  );
}

/**
 * Command new pan and tilt angles while applying hardware saturation bounds.
 */
export function commandPanTilt(
  camera: CameraState,
  panCmdRad: number,
  tiltCmdRad: number
): [CameraState, ClampReport] {
  let panClamped = false;
  let tiltClamped = false;

  let pan = panCmdRad;
  let tilt = tiltCmdRad;

  if (pan < camera.pan_min_rad) {
    pan = camera.pan_min_rad;
    panClamped = true;
  } else if (pan > camera.pan_max_rad) {
    pan = camera.pan_max_rad;
    panClamped = true;
  }

  if (tilt < camera.tilt_min_rad) {
    tilt = camera.tilt_min_rad;
    tiltClamped = true;
  } else if (tilt > camera.tilt_max_rad) {
    tilt = camera.tilt_max_rad;
    tiltClamped = true;
  }

  return [
    { ...camera, pan_rad: pan, tilt_rad: tilt },
    { pan_clamped: panClamped, tilt_clamped: tiltClamped }
  ];
}
