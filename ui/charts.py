"""ui/charts.py -- RollingChart and LockStateIndicator widgets."""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.contracts import TrackState
from ui.palette import (
    BG_INSET,
    BG_PANEL,
    LINE,
    LINE_STRONG,
    STATE_COLORS,
    TEXT_0,
    TEXT_1,
    TEXT_2,
)

# CRITICAL RUNTIME ASSERTION: Enforce single source of truth mapping for all TrackState enum members
assert set(STATE_COLORS.keys()) == set(TrackState), (
    f"STATE_COLORS must exhaustively map all TrackState enum members without fallbacks. "
    f"Expected {set(TrackState)}, got {set(STATE_COLORS.keys())}"
)


class LockStateIndicator(QWidget):
    """230px mission-critical lock-state banner.

    Fills block with state color at ~12% alpha, 1px solid border, ~34px bold mono text.
    LOST state blinks at 1 Hz. Imports STATE_COLORS from palette.py as single source of truth.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(230, 80)
        self.setFixedHeight(80)

        # Enforce exhaustive mapping assertion on import/instantiation
        assert set(STATE_COLORS.keys()) == set(TrackState), (
            "LockStateIndicator requires STATE_COLORS from palette.py to match set(TrackState) exactly."
        )

        self._state: TrackState = TrackState.SEARCH
        self._blink_visible: bool = True

        # 1 Hz blink timer (500 ms toggle) for LOST state
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.start()

    def set_state(self, state: TrackState) -> None:
        """Update current tracking state."""
        if self._state != state:
            self._state = state
            self._blink_visible = True
            self.update()

    def _toggle_blink(self) -> None:
        if self._state == TrackState.LOST:
            self._blink_visible = not self._blink_visible
            self.update()
        elif not self._blink_visible:
            self._blink_visible = True
            self.update()

    def paintEvent(self, event) -> None:
        """Paint 230px banner block with 12% alpha fill, solid border, and ~34px bold mono text."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        # Exhaustive lookup -- NO fallback/default branch. If state is unmapped, KeyError fires loudly.
        hex_color = STATE_COLORS[self._state]
        base_color = QColor(hex_color)

        # Calculate ~12% alpha fill (30/255)
        if self._state == TrackState.LOST and not self._blink_visible:
            fill_color = QColor(BG_INSET)
            border_color = QColor(LINE_STRONG)
            text_color = QColor(TEXT_2)
        else:
            fill_color = QColor(base_color.red(), base_color.green(), base_color.blue(), int(255 * 0.12))
            border_color = base_color
            text_color = base_color

        # Fill background block
        painter.fillRect(rect, fill_color)

        # Solid 1px border
        painter.setPen(QPen(border_color, 1.5))
        painter.drawRect(rect)

        # State text in ~34px bold monospace
        font = QFont("Consolas", 32, QFont.Weight.Bold)
        font.setStyleHint(QFont.StyleHint.Monospace)
        painter.setFont(font)
        painter.setPen(QPen(text_color))

        state_name = self._state.value
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, state_name)


class RollingChart(QWidget):
    """Rolling line chart widget for telemetry metrics (FPS, Tracking Error, Lock Fraction)."""

    def __init__(
        self,
        title: str,
        line_color_hex: str = "#00E676",
        min_val: float = 0.0,
        max_val: float = 100.0,
        capacity: int = 150,
        unit_str: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.line_color = QColor(line_color_hex)
        self.min_val = min_val
        self.max_val = max_val
        self.unit_str = unit_str
        self.capacity = capacity

        self._buffer: Deque[Tuple[float, float]] = deque(maxlen=capacity)
        self.setMinimumSize(180, 70)

    def push(self, timestamp_s: float, value: float) -> None:
        """Push new data sample into rolling chart buffer."""
        self._buffer.append((timestamp_s, value))
        self.update()

    def clear(self) -> None:
        """Clear data buffer."""
        self._buffer.clear()
        self.update()

    def paintEvent(self, event) -> None:
        """Paint rolling trend line chart with background frame and gridlines."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect())
        painter.fillRect(rect, QColor(BG_INSET))
        painter.setPen(QPen(QColor(LINE), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        # Title & current value header
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(TEXT_1)))
        painter.drawText(QPointF(6, 14), self.title.upper())

        latest_val = self._buffer[-1][1] if self._buffer else 0.0
        val_str = f"{latest_val:.1f}{self.unit_str}"
        font_val = QFont("Consolas", 10, QFont.Weight.Bold)
        painter.setFont(font_val)
        painter.setPen(QPen(QColor(TEXT_0)))

        fm = painter.fontMetrics()
        w_val = fm.horizontalAdvance(val_str)
        painter.drawText(QPointF(rect.width() - w_val - 6, 14), val_str)

        # Plot area dimensions
        plot_rect = rect.adjusted(6, 20, -6, -6)
        w_plot = plot_rect.width()
        h_plot = plot_rect.height()

        if w_plot <= 0 or h_plot <= 0:
            return

        # Grid lines
        painter.setPen(QPen(QColor(LINE), 0.5, Qt.PenStyle.DotLine))
        painter.drawLine(QPointF(plot_rect.left(), plot_rect.top() + h_plot / 2), QPointF(plot_rect.right(), plot_rect.top() + h_plot / 2))

        if len(self._buffer) < 2:
            return

        # Dynamically scale y-range if values exceed static bounds
        vals = [v for _, v in self._buffer]
        cur_min = min(self.min_val, min(vals))
        cur_max = max(self.max_val, max(vals))
        y_range = max(1e-5, cur_max - cur_min)

        # Compute plot polyline points
        points = []
        n = len(self._buffer)
        for i, (_, val) in enumerate(self._buffer):
            x = plot_rect.left() + (i / float(self.capacity - 1)) * w_plot
            norm_y = (val - cur_min) / y_range
            y = plot_rect.bottom() - norm_y * h_plot
            points.append(QPointF(x, y))

        # Render trend line
        painter.setPen(QPen(self.line_color, 1.5))
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])
