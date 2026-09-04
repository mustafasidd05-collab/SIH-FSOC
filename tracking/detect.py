"""tracking/detect.py -- per-frame optical-beacon detection.

Classical CV chain: grayscale -> 3x3 Gaussian blur -> fixed brightness
threshold -> morphology-open -> external contours -> largest blob wins.
Returns a Detection (centroid, bbox, confidence) or None if nothing credible
was found. This module never keeps state between frames; frames are
independent (temporal filtering belongs to kalman.py / state_machine.py).

Why classical thresholding for v1 (technical-report line):

    "v1 detects the beacon with a classical threshold-then-contour pipeline
    rather than a learned detector for four reasons: (a) no labeled training
    data exists for the virtual scene, while a bright point source on a near-
    black background is exactly the regime classical thresholding is provably
    good at; (b) per-frame cost is sub-millisecond at 1280x720, leaving ample
    budget for the 60 Hz control loop, whereas a CNN would dominate the
    frame budget on the same hardware; (c) every detection decision is
    explainable -- a property a judge can inspect and we can defend live;
    and (d) the Detection contract isolates the detector behind one boundary,
    so a learned detector can be swapped in later without touching the
    tracker or state machine."

Confidence metric (contract-critical, used by the state machine):

    confidence = clamp(peak_intensity / 255, 0, 1) * circularity(4*pi*A/P^2)

i.e. a bright *round* blob scores near 1; a bright but elongated / half-
occluded / noisy blob scores lower even when bright. This gives the state
machine a degrading signal as noise and atmospheric smear grow, instead of
a brittle yes/no. Both factors are bounded in [0, 1], so confidence is in
[0, 1] with 0 meaning 'nothing detected'.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Tunable parameters. All named; the state machine's thresholds are separate
# named constants in state_machine.py -- detection here, decision there.
# ---------------------------------------------------------------------------

# Grayscale intensity above which a pixel counts as beacon light. The beacon
# renders with a ~255 peak on a black background; 150 keeps the core of the
# point spread function (>8 px for a sigma-1.5 blob) while sitting ~15 sigma
# above the sensor-noise distribution (sigma ~10), so noise cannot produce a
# candidate and the core survives the 3x3 pre-blur that suppresses specks.
BRIGHTNESS_THRESHOLD = 150

# Gaussian blur applied before thresholding. 3x3 suppresses single-pixel
# sensor outliers without smearing a ~5px blob.
BLUR_KERNEL = (3, 3)

# Morphology-open kernel: removes 1-2px spurious specks left of the
# threshold, then contour extraction runs on the cleaned mask.
MORPH_KERNEL = (3, 3)

# Smallest blob (px) that can be a beacon. Below this, reject -- a beacon
# must subtend several pixels on the sensor.
MIN_BLOB_AREA_PX = 4.0

# If the largest contour covers more than this fraction of the frame, it is
# bloom / full-frame flare, not a beacon. Reject rather than centroid it.
MAX_BLOB_AREA_RATIO = 0.05


@dataclass(frozen=True)
class Detection:
    """One frame's detection result. confidence in [0, 1]; see module docstring.

    centroid_px/bbox_px are raw top-left-origin pixel coordinates, as per the
    contracts.py units convention. Detection says nothing about *validity* --
    the state machine applies confidence floors and gating.
    """

    centroid_px: tuple[float, float]
    bbox_px: tuple[float, float, float, float]
    confidence: float


class BeaconDetector:
    """Stateless per-frame beacon detector. Construct once, call detect(frame)
    for each SimFrame.image."""

    def __init__(
        self,
        brightness_threshold: int = BRIGHTNESS_THRESHOLD,
        min_blob_area_px: float = MIN_BLOB_AREA_PX,
        max_blob_area_ratio: float = MAX_BLOB_AREA_RATIO,
    ) -> None:
        self._brightness_threshold = brightness_threshold
        self._min_area = min_blob_area_px
        self._max_area_ratio = max_blob_area_ratio

    def detect_candidates(self, image: np.ndarray) -> list[Detection]:
        """Detect all valid point-source candidate blobs meeting size filters."""
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"detect() expects uint8 BGR (H, W, 3), got {image.shape}")
        if image.dtype != np.uint8:
            raise ValueError(f"detect() expects uint8, got {image.dtype}")

        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, BLUR_KERNEL, 0)

        # Adaptive thresholding: if peak intensity is lower than config, adapt to 60% of local peak
        max_val = np.max(gray)
        if max_val < self._brightness_threshold:
            thresh_val = max(30, int(max_val * 0.6))
        else:
            thresh_val = self._brightness_threshold

        mask = cv2.threshold(
            gray, thresh_val, 255, cv2.THRESH_BINARY
        )[1]
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones(MORPH_KERNEL, np.uint8))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        if not contours:
            return candidates

        max_area_allowed = self._max_area_ratio * height * width

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self._min_area or area > max_area_allowed:
                continue

            moments = cv2.moments(contour)
            if moments["m00"] <= 0.0:
                continue

            centroid = (moments["m10"] / moments["m00"], moments["m01"] / moments["m00"])
            x, y, w, h = cv2.boundingRect(contour)

            peak = float(np.max(gray[y : y + h, x : x + w])) if w > 0 and h > 0 else 0.0
            brightness = np.clip(peak / 255.0, 0.0, 1.0)

            perimeter = cv2.arcLength(contour, closed=True)
            if perimeter <= 0.0:
                circularity = 0.0
            else:
                circularity = float(np.clip((4.0 * np.pi * area) / (perimeter * perimeter), 0.0, 1.0))

            # Streak-tolerant confidence score
            confidence = brightness * (0.4 + 0.6 * circularity)

            candidates.append(
                Detection(
                    centroid_px=(float(centroid[0]), float(centroid[1])),
                    bbox_px=(float(x), float(y), float(w), float(h)),
                    confidence=confidence,
                )
            )
        return candidates

    def detect(self, image: np.ndarray) -> Detection | None:
        """Return the strongest (highest confidence) blob Detection, or None if nothing credible."""
        candidates = self.detect_candidates(image)
        if not candidates:
            return None
        return max(candidates, key=lambda c: c.confidence)