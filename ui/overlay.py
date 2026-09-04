"""ui/overlay.py -- VideoPane widget with scaled QImage display and QPainter HUD overlay."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Optional, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Signal, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from core.contracts import TelemetryPacket, TrackState
from ui.palette import (
    BG_INSET,
    BG_ROOT,
    LINE,
    STATE_COLORS,
    TEXT_0,
    TEXT_1,
    TEXT_2,
)


class VideoPane(QWidget):
    """Widget displaying virtual camera video with rich QPainter HUD overlays."""

    target_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 320)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Click a visible target to acquire it")

        self._image: Optional[QImage] = None
        self._packet: Optional[TelemetryPacket] = None
        self._img_width = 640
        self._img_height = 480

        # Base dark background brush
        self._bg_color = QColor(BG_ROOT)

    def update_frame(self, packet: TelemetryPacket, image_bgr: np.ndarray) -> None:
        """Update pane with new frame image and telemetry packet."""
        self._packet = packet

        h, w, c = image_bgr.shape
        self._img_width = w
        self._img_height = h

        # Convert numpy BGR to QImage (Format_BGR888)
        bytes_per_line = w * c
        # Copy buffer to ensure safe memory management
        self._image = QImage(
            image_bgr.data.tobytes(),
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_BGR888,
        )

        self.update()

    def paintEvent(self, event) -> None:
        """Paint video frame scaled to aspect ratio with mission-control HUD overlay."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Clear background
        rect = self.rect()
        painter.fillRect(rect, self._bg_color)

        if self._image is None or self._image.isNull():
            # Render placeholder string when no video feed
            painter.setPen(QPen(QColor(TEXT_2)))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "NO VIDEO FEED")
            return

        video_rect = self._video_rect()
        target_x = video_rect.x()
        target_y = video_rect.y()
        target_w = video_rect.width()
        target_h = video_rect.height()

        # Draw video frame
        painter.drawImage(video_rect, self._image)

        # Draw frame border
        painter.setPen(QPen(QColor(LINE), 1))
        painter.drawRect(video_rect)

        # Coordinate transformation lambda: image space (0..W, 0..H) -> widget space
        scale_x = target_w / float(self._img_width)
        scale_y = target_h / float(self._img_height)

        def img_to_widget(x_img: float, y_img: float) -> QPointF:
            return QPointF(target_x + x_img * scale_x, target_y + y_img * scale_y)

        # Determine current state color accent
        state = self._packet.track_state if self._packet else TrackState.SEARCH
        accent_hex = STATE_COLORS.get(state, "#FFB300")
        accent_color = QColor(accent_hex)

        boresight_img = (self._img_width / 2.0, self._img_height / 2.0)
        boresight_w = img_to_widget(boresight_img[0], boresight_img[1])

        # 1. Boresight Reticle / Center Crosshair
        self._draw_reticle(painter, boresight_w, accent_color)

        # 2. Target Centroid, Bounding Box, and Error Vector
        if self._packet and state != TrackState.LOST:
            err_x, err_y = self._packet.error_px
            centroid_img_x = boresight_img[0] + err_x
            centroid_img_y = boresight_img[1] + err_y
            centroid_w = img_to_widget(centroid_img_x, centroid_img_y)

            # Draw dashed error vector line
            pen_dash = QPen(accent_color, 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen_dash)
            painter.drawLine(boresight_w, centroid_w)

            # Error distance label
            err_dist_px = math.hypot(err_x, err_y)
            mid_w = QPointF((boresight_w.x() + centroid_w.x()) / 2.0, (boresight_w.y() + centroid_w.y()) / 2.0)
            painter.setFont(QFont("Consolas", 9))
            painter.setPen(QPen(accent_color))
            painter.drawText(mid_w + QPointF(8, -4), f"{err_dist_px:.1f}px")

            # Draw Bounding Box around centroid
            bbox_size_img = 24.0 if state == TrackState.TRACK else 40.0
            bbox_top_left = img_to_widget(centroid_img_x - bbox_size_img / 2.0, centroid_img_y - bbox_size_img / 2.0)
            bbox_w = bbox_size_img * scale_x
            bbox_h = bbox_size_img * scale_y
            bbox_rect = QRectF(bbox_top_left.x(), bbox_top_left.y(), bbox_w, bbox_h)

            pen_bbox = QPen(accent_color, 1.5)
            painter.setPen(pen_bbox)
            painter.drawRect(bbox_rect)

            # Corner brackets on bbox
            corner_len = min(8.0, bbox_w / 3.0)
            self._draw_corner_brackets(painter, bbox_rect, accent_color, corner_len)

            # Target Centroid Marker (Cross + Dot)
            painter.setPen(QPen(accent_color, 1.5))
            painter.drawLine(
                QPointF(centroid_w.x() - 5, centroid_w.y()),
                QPointF(centroid_w.x() + 5, centroid_w.y()),
            )
            painter.drawLine(
                QPointF(centroid_w.x(), centroid_w.y() - 5),
                QPointF(centroid_w.x(), centroid_w.y() + 5),
            )
            painter.setBrush(accent_color)
            painter.drawEllipse(centroid_w, 2.5, 2.5)

        # 3. 4-Corner Monochrome HUD
        self._draw_hud(painter, video_rect, accent_color)

    def _video_rect(self) -> QRectF:
        """Rectangle occupied by the aspect-fitted image inside the widget."""
        w_widget = self.rect().width()
        h_widget = self.rect().height()
        aspect_img = self._img_width / float(self._img_height)
        aspect_widget = w_widget / float(h_widget)

        if aspect_widget > aspect_img:
            target_h = h_widget
            target_w = int(target_h * aspect_img)
            target_x = (w_widget - target_w) // 2
            target_y = 0
        else:
            target_h = int(target_w / aspect_img)
            target_x = 0
            target_y = (h_widget - target_h) // 2
        return QRectF(target_x, target_y, target_w, target_h)

    def mousePressEvent(self, event) -> None:
        """Emit the image-space location selected by the operator."""
        video_rect = self._video_rect()
        position = event.position()
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._image is not None
            and video_rect.contains(position)
        ):
            x_img = (position.x() - video_rect.left()) * self._img_width / video_rect.width()
            y_img = (position.y() - video_rect.top()) * self._img_height / video_rect.height()
            self.target_selected.emit((float(x_img), float(y_img)))
        super().mousePressEvent(event)


    def _draw_reticle(self, painter: QPainter, center: QPointF, color: QColor) -> None:
        """Draw central boresight crosshair and target reticle."""
        cx, cy = center.x(), center.y()
        r = 16.0
        gap = 4.0

        pen = QPen(color, 1.0)
        painter.setPen(pen)

        # Reticle circle
        painter.drawEllipse(center, r, r)

        # Crosshair ticks with center gap
        painter.drawLine(QPointF(cx - r - 8, cy), QPointF(cx - gap, cy))
        painter.drawLine(QPointF(cx + gap, cy), QPointF(cx + r + 8, cy))
        painter.drawLine(QPointF(cx, cy - r - 8), QPointF(cx, cy - gap))
        painter.drawLine(QPointF(cx, cy + gap), QPointF(cx, cy + r + 8))

    def _draw_corner_brackets(
        self, painter: QPainter, rect: QRectF, color: QColor, length: float
    ) -> None:
        """Draw 4 corner bracket accents on target bounding box."""
        pen = QPen(color, 2.0)
        painter.setPen(pen)

        l, t, r, b = rect.left(), rect.top(), rect.right(), rect.bottom()

        # Top-Left
        painter.drawLine(QPointF(l, t), QPointF(l + length, t))
        painter.drawLine(QPointF(l, t), QPointF(l, t + length))

        # Top-Right
        painter.drawLine(QPointF(r, t), QPointF(r - length, t))
        painter.drawLine(QPointF(r, t), QPointF(r, t + length))

        # Bottom-Left
        painter.drawLine(QPointF(l, b), QPointF(l + length, b))
        painter.drawLine(QPointF(l, b), QPointF(l, b - length))

        # Bottom-Right
        painter.drawLine(QPointF(r, b), QPointF(r - length, b))
        painter.drawLine(QPointF(r, b), QPointF(r, b - length))

    def _draw_hud(self, painter: QPainter, rect: QRectF, accent_color: QColor) -> None:
        """Draw 4-corner telemetry HUD inside video viewport."""
        font_mono = QFont("Consolas", 10)
        font_mono.setStyleHint(QFont.StyleHint.Monospace)
        painter.setFont(font_mono)

        margin = 12.0
        top = rect.top() + margin
        bottom = rect.bottom() - margin
        left = rect.left() + margin
        right = rect.right() - margin

        pkt = self._packet
        fps = pkt.fps if pkt else 30.0
        frame_id = pkt.frame_id if pkt else 0
        state_str = pkt.track_state.value if pkt else "SEARCH"
        az_rad = pkt.error_az_rad if pkt else 0.0
        el_rad = pkt.error_el_rad if pkt else 0.0
        lock_pct = (pkt.lock_fraction * 100.0) if pkt else 0.0
        acq_s = pkt.acquisition_time_s if pkt else float("nan")

        # Top-Left HUD: State Chip & FPS
        painter.setPen(QPen(accent_color))
        state_chip = f"[{state_str}]"
        painter.drawText(QPointF(left, top + 10), state_chip)

        painter.setPen(QPen(QColor(TEXT_0)))
        painter.drawText(QPointF(left + 100, top + 10), f"{fps:.1f} FPS")

        # Top-Right HUD: UTC Clock & Frame Number
        now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S")
        right_text_1 = f"F#{frame_id:06d} | {now_utc} UTC"
        fm = painter.fontMetrics()
        w_text_1 = fm.horizontalAdvance(right_text_1)
        painter.drawText(QPointF(right - w_text_1, top + 10), right_text_1)

        # Bottom-Left HUD: Azimuth / Elevation rad
        left_text_2 = f"AZ: {az_rad:+0.4f} rad   EL: {el_rad:+0.4f} rad"
        painter.drawText(QPointF(left, bottom), left_text_2)

        # Bottom-Right HUD: Lock fraction & Acquisition Time
        acq_str = f"{acq_s:.2f}s" if not math.isnan(acq_s) else "N/A"
        right_text_2 = f"LOCK: {lock_pct:5.1f}% | ACQ: {acq_str}"
        w_text_2 = fm.horizontalAdvance(right_text_2)
        painter.drawText(QPointF(right - w_text_2, bottom), right_text_2)
