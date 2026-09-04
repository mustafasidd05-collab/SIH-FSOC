"""core/camera/input_adapter.py -- Benchmark-2 MP4 video input adapter.

Bypasses the virtual scene generator and virtual camera to feed an external
pre-recorded .mp4 video file into the downstream tracking, filtering, and control
pipeline, fulfilling Benchmark Performance-2 requirements.
"""

from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np

from core.contracts import CameraState, SimFrame


class VideoInputAdapter:
    """Reads frames sequentially from an external .mp4 video file as SimFrames.

    Parameters
    ----------
    video_path : str | Path
        Path to the input .mp4 video file.
    camera : CameraState | None
        Optional override for camera optics/state. If None, constructed from video properties.
    loop : bool
        Whether to loop the video when reaching the end.
    """

    def __init__(
        self,
        video_path: str | Path,
        camera: CameraState | None = None,
        loop: bool = False,
    ) -> None:
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {self.video_path}")

        self.cap = cv2.VideoCapture(str(self.video_path))
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError(f"Failed to open video file: {self.video_path}")

        self.width_px = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height_px = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 30.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.loop = loop

        self._frame_id = 0

        if camera is not None:
            self.camera = camera
        else:
            self.camera = CameraState(
                pan_rad=0.0,
                tilt_rad=0.0,
                pan_min_rad=-1.57,
                pan_max_rad=1.57,
                tilt_min_rad=-1.57,
                tilt_max_rad=1.57,
                fov_h_rad=0.7,
                fov_v_rad=0.5,
                width_px=self.width_px,
                height_px=self.height_px,
            )

    @property
    def fps_val(self) -> float:
        return self.fps

    def read_frame(self) -> SimFrame | None:
        """Read the next frame from the video file and return as a SimFrame, or None on EOF."""
        ret, bgr_frame = self.cap.read()
        if not ret:
            if self.loop:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, bgr_frame = self.cap.read()
                if not ret:
                    return None
            else:
                return None

        # Ensure correct resolution if video differs from camera config
        if bgr_frame.shape[1] != self.camera.width_px or bgr_frame.shape[0] != self.camera.height_px:
            bgr_frame = cv2.resize(bgr_frame, (self.camera.width_px, self.camera.height_px))

        timestamp_s = self._frame_id / self.fps
        sim_frame = SimFrame(
            frame_id=self._frame_id,
            timestamp_s=timestamp_s,
            image=bgr_frame,
            camera=self.camera,
        )
        self._frame_id += 1
        return sim_frame

    def release(self) -> None:
        """Release the video capture handle."""
        if self.cap.isOpened():
            self.cap.release()

    def __enter__(self) -> VideoInputAdapter:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
