"""Unit tests for tracking/detect.py -- classical threshold + contour detector.

Verification style: known synthetic frames -> expected geometric facts
(hand-computed centroids, rejection cases), not internal implementation
details.
"""

import cv2
import numpy as np
import pytest

from tests.fixtures.generate_clips import BLUR_KERNEL, BLUR_SIGMA, load_clip
from tracking.detect import BeaconDetector


def _frame_with_blob(
    center: tuple[int, int],
    radius: int = 3,
    peak: int = 255,
    size: tuple[int, int] = (1280, 720),
) -> np.ndarray:
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    cv2.circle(img, center, radius, (peak, peak, peak), -1)
    return cv2.GaussianBlur(img, BLUR_KERNEL, BLUR_SIGMA)


def test_detects_blob_with_correct_centroid():
    # Hand-computed expectation: a circular blob centered at (640, 360) must
    # centroid within 1.5 px of its geometric center (sub-pixel quantization
    # of the blurred, thresholded mask).
    frame = _frame_with_blob((640, 360))
    det = BeaconDetector().detect(frame)
    assert det is not None
    cx, cy = det.centroid_px
    assert abs(cx - 640.0) <= 1.5
    assert abs(cy - 360.0) <= 1.5
    # Bright + round => high confidence.
    assert det.confidence >= 0.6
    assert det.confidence <= 1.0
    # bbox wraps the blob and stays inside the frame.
    x, y, w, h = det.bbox_px
    assert w > 0 and h > 0
    assert 0 <= x and x + w <= 1280
    assert 0 <= y and y + h <= 720


def test_detects_blob_off_center():
    frame = _frame_with_blob((200, 500))
    det = BeaconDetector().detect(frame)
    assert det is not None
    cx, cy = det.centroid_px
    assert abs(cx - 200.0) <= 1.5
    assert abs(cy - 500.0) <= 1.5


def test_empty_frame_returns_none():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert BeaconDetector().detect(frame) is None


def test_single_bright_pixel_rejected():
    # One saturated pixel has area 1 < MIN_BLOB_AREA_PX (4): not a beacon.
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[360, 640] = (255, 255, 255)
    det = BeaconDetector().detect(frame)
    assert det is None


def test_dim_blob_gets_lower_confidence_than_bright_blob():
    # A dimmer beacon is still geometrically detectable, but its brightness
    # factor must pull confidence below a fully-saturated beacon's.
    dim = _frame_with_blob((640, 360), peak=205)
    bright = _frame_with_blob((640, 360), peak=255)

    det_dim = BeaconDetector().detect(dim)
    det_bright = BeaconDetector().detect(bright)
    assert det_dim is not None
    assert det_bright is not None
    assert 0.0 < det_dim.confidence < det_bright.confidence <= 1.0


def test_confidence_bounded_on_noisy_frame():
    rng = np.random.default_rng(7)
    frame = _frame_with_blob((400, 300))
    noise = rng.normal(0.0, 10.0, frame.shape)
    frame = np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    det = BeaconDetector().detect(frame)
    assert det is not None
    assert 0.0 <= det.confidence <= 1.0
    cx, cy = det.centroid_px
    assert abs(cx - 400.0) <= 4.0  # noise moves the centroid, but not far
    assert abs(cy - 300.0) <= 4.0


def test_rejects_wrong_input_types():
    det = BeaconDetector()
    with pytest.raises(ValueError):
        det.detect(np.zeros((720, 1280), dtype=np.uint8))  # 2D, not BGR
    with pytest.raises(ValueError):
        det.detect(np.zeros((720, 1280, 3), dtype=np.float32))  # wrong dtype


def test_agrees_with_clip_ground_truth_on_first_frame():
    # The canonical clean-clip frame: detector must find the beacon at the
    # analytic path position (this pins the clip + detector together).
    clip = load_clip("clip_clean")
    det = BeaconDetector().detect(clip["images"][0])
    assert det is not None
    gt_x, gt_y = clip["gt_xy"][0]
    assert abs(det.centroid_px[0] - gt_x) <= 2.0
    assert abs(det.centroid_px[1] - gt_y) <= 2.0
    assert det.confidence >= 0.6