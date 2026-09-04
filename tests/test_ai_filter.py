"""Unit tests for tracking/ai_filter.py."""

import numpy as np
import pytest

from tracking.ai_filter import AIFilter


def test_ai_filter_heuristic_scoring():
    ai = AIFilter()
    
    # Bright spot patch
    bright_patch = np.full((32, 32, 3), 20, dtype=np.uint8)
    bright_patch[12:20, 12:20] = 255
    score_bright = ai.score_patch(bright_patch)

    # Uniform dark patch
    dark_patch = np.full((32, 32, 3), 10, dtype=np.uint8)
    score_dark = ai.score_patch(dark_patch)

    assert score_bright > score_dark
    assert 0.0 <= score_bright <= 1.0
    assert 0.0 <= score_dark <= 1.0


def test_ai_filter_candidates():
    ai = AIFilter(confidence_threshold=0.1)
    frame = np.full((200, 200, 3), 15, dtype=np.uint8)
    frame[90:110, 90:110] = 255  # bright beacon

    candidates = [{"centroid": (100.0, 100.0), "bbox": (90, 90, 20, 20)}]
    filtered = ai.filter_candidates(frame, candidates)
    assert len(filtered) == 1
    assert filtered[0]["ai_score"] > 0.1
