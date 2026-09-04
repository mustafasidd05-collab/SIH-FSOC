"""CNN-backed candidate ranking for beacon detection.
The shipped application loads an optional ONNX model through OpenCV DNN, so it
does not need PyTorch at runtime. Without a model, a deterministic contrast
heuristic keeps the classical detector operational. A trajectory reference can
restrict candidates to the Kalman gate, preventing a new bright object from
stealing an established lock.
"""

from __future__ import annotations
import math
from pathlib import Path
import cv2
import numpy as np

from .detect import Detection


class AIFilter:
    """ONNX CNN candidate classifier with a deterministic heuristic fallback."""


    def __init__(
        self,
        model_path: str | Path | None = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        self.confidence_threshold = confidence_threshold
        self._net: cv2.dnn.Net | None = None
        self._model_loaded = False
        self.model_path: Path | None = None


        default_model = Path(__file__).with_name("model.onnx")
        path = Path(model_path) if model_path is not None else default_model
        if path.exists():
            if path.suffix.lower() != ".onnx":
                raise ValueError("runtime AI model must be an ONNX file")
            try:
                self._net = cv2.dnn.readNetFromONNX(str(path))
            except cv2.error as exc:
                raise RuntimeError(f"failed to load ONNX model {path}: {exc}") from exc
            self.model_path = path
            self._model_loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._model_loaded

    def score_patch(self, patch_bgr: np.ndarray) -> float:
        """Score an image patch (H x W x 3) returning confidence in [0.0, 1.0]."""
        if patch_bgr is None or patch_bgr.size == 0:
            return 0.0

        resized = cv2.resize(patch_bgr, (32, 32), interpolation=cv2.INTER_AREA)
        gray = (
            cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            if resized.ndim == 3
            else resized
        )

        if self._net is not None:
            blob = gray.astype(np.float32)[None, None, ...] / 255.0
            self._net.setInput(blob)
            output = self._net.forward()
            logit = float(np.asarray(output).reshape(-1)[0])
            if logit >= 0.0:
                return float(1.0 / (1.0 + math.exp(-logit)))
            exp_logit = math.exp(logit)
            return float(exp_logit / (1.0 + exp_logit))

        # Fallback heuristic scoring based on brightness and circularity

        peak = float(np.max(gray))
        mean_val = float(np.mean(gray))
        contrast = peak - mean_val

        # Higher contrast and brightness -> higher likelihood of being a true beacon
        score = min(1.0, max(0.0, contrast / 200.0 * (peak / 255.0)))
        return float(score)

    def filter_candidates(self, frame: np.ndarray, candidates: list[dict]) -> list[dict]:
        """Filter a list of candidate detections using patch scoring."""
        filtered = []
        h, w = frame.shape[:2]
        patch_size = 16  # half-size

        for cand in candidates:
            cx, cy = int(cand["centroid"][0]), int(cand["centroid"][1])
            x0 = max(0, cx - patch_size)
            x1 = min(w, cx + patch_size)
            y0 = max(0, cy - patch_size)
            y1 = min(h, cy + patch_size)

            patch = frame[y0:y1, x0:x1]
            score = self.score_patch(patch)
            cand["ai_score"] = score

            if score >= self.confidence_threshold:
                filtered.append(cand)

        return filtered

    def select_best_candidate(
        self,
        image: np.ndarray,
        candidates: list[Detection],
        *,
        reference_px: tuple[float, float] | None = None,
        gate_radius_px: float | None = None,
    ) -> Detection | None:
        """Select a candidate by CNN score, optionally constrained by a spatial gate."""
        if not candidates:
            return None

        eligible = candidates
        if reference_px is not None and gate_radius_px is not None:
            eligible = [
                candidate
                for candidate in candidates
                if math.dist(candidate.centroid_px, reference_px) <= gate_radius_px
            ]
            if not eligible:
                return None

        scored: list[tuple[float, Detection]] = []
        for candidate in eligible:
            ai_score = self.score_patch(
                self._extract_patch(image, candidate.centroid_px)
            )
            if self.is_loaded and ai_score < self.confidence_threshold:
                continue


            total_score = 0.3 * candidate.confidence + 0.7 * ai_score
            if reference_px is not None and gate_radius_px:
                proximity = 1.0 - min(
                    math.dist(candidate.centroid_px, reference_px) / gate_radius_px,
                    1.0,
                )
                total_score = 0.55 * proximity + 0.15 * candidate.confidence + 0.30 * ai_score
            scored.append((total_score, candidate))

        return max(scored, key=lambda item: item[0])[1] if scored else None

    def _extract_patch(self, image: np.ndarray, centroid: tuple[float, float]) -> np.ndarray:
        """Extract a 32x32 patch centered at the given centroid."""
        h, w = image.shape[:2]
        cx, cy = int(centroid[0]), int(centroid[1])
        x0 = max(0, cx - 16)
        x1 = min(w, cx + 16)
        y0 = max(0, cy - 16)
        y1 = min(h, cy + 16)

        patch = image[y0:y1, x0:x1]
        if patch.shape[0] != 32 or patch.shape[1] != 32:
            shape = (32, 32, image.shape[2]) if image.ndim == 3 else (32, 32)
            padded = np.zeros(shape, dtype=image.dtype)
            ph, pw = patch.shape[:2]
            padded[:ph, :pw] = patch
            return padded
        return patch
