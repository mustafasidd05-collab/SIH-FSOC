"""Unit tests for core/camera/input_adapter.py (Benchmark-2 MP4 video input)."""

import numpy as np
import pytest
from pathlib import Path
import cv2

from core.camera.input_adapter import VideoInputAdapter
from core.contracts import SimFrame


@pytest.fixture
def temp_video(tmp_path):
    """Create a short temporary .mp4 video file using OpenCV for testing."""
    video_path = tmp_path / "test_beacon.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = 30.0
    width, height = 320, 240
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))

    for i in range(15):
        img = np.zeros((height, width, 3), dtype=np.uint8)
        # Draw a moving white circle as the beacon
        cv2.circle(img, (50 + i * 10, 120), 5, (255, 255, 255), -1)
        writer.write(img)

    writer.release()
    return video_path


def test_video_input_adapter_reads_frames(temp_video):
    with VideoInputAdapter(temp_video) as adapter:
        assert adapter.width_px == 320
        assert adapter.height_px == 240
        assert adapter.fps_val == 30.0

        frame = adapter.read_frame()
        assert isinstance(frame, SimFrame)
        assert frame.frame_id == 0
        assert frame.image.shape == (240, 320, 3)
        assert frame.timestamp_s == 0.0

        # Read remaining frames
        count = 1
        while f := adapter.read_frame():
            count += 1
            assert isinstance(f, SimFrame)

        assert count == 15
