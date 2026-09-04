"""Human-readable live and archived telemetry analytics window."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Sequence

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPointF,
    QRegularExpression,
    QRectF,
    QSortFilterProxyModel,
    Signal,
    QTimer,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.contracts import TelemetryPacket, TrackState
from telemetry.performance_logger import PerformanceLogger
from ui.palette import (
    BG_INSET,
    LINE,
    LINE_STRONG,
    STATE_COLORS,
    TEXT_0,
    TEXT_1,
    TEXT_2,
)


def _number_or_nan(value: object) -> float:
    """Convert persisted JSON numbers and nulls to the telemetry float shape."""
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected a number or null, received {value!r}") from exc


def load_performance_log(filepath: str | Path) -> PerformanceLogger:
    """Load an exported performance log for read-only analysis.

    Logs produced before angular-error and loop-time export support remain readable;
    those absent values are displayed as N/A.
    """
    path = Path(filepath)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read performance log: {exc}") from exc

    rows = payload.get("packets") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Performance log must contain a 'packets' array")

    logger = PerformanceLogger()
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Packet {row_number} is not an object")
        error_px = row.get("error_px", [None, None])
        if not isinstance(error_px, (list, tuple)) or len(error_px) != 2:
            raise ValueError(f"Packet {row_number} has an invalid error_px value")
        try:
            packet = TelemetryPacket(
                frame_id=int(row["frame_id"]),
                timestamp_s=_number_or_nan(row.get("timestamp_s")),
                fps=_number_or_nan(row.get("fps")),
                track_state=TrackState(str(row["track_state"])),
                error_px=(
                    _number_or_nan(error_px[0]),
                    _number_or_nan(error_px[1]),
                ),
                error_az_rad=_number_or_nan(row.get("error_az_rad")),
                error_el_rad=_number_or_nan(row.get("error_el_rad")),
                lock_fraction=_number_or_nan(row.get("lock_fraction")),
                acquisition_time_s=_number_or_nan(row.get("acquisition_time_s")),
                loop_time_s=_number_or_nan(row.get("loop_time_s")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Packet {row_number} is invalid: {exc}") from exc
        logger.record(packet)
    return logger


class TelemetryTableModel(QAbstractTableModel):
    """Typed table model exposing every telemetry packet field."""

    HEADERS = (
        "FRAME",
        "TIME (s)",
        "STATE",
        "FPS",
        "LOOP (ms)",
        "ERR X (px)",
        "ERR Y (px)",
        "ERR MAG (px)",
        "AZ ERR (mrad)",
        "EL ERR (mrad)",
        "LOCK (%)",
        "ACQ (s)",
    )

    def __init__(
        self,
        packets: Sequence[TelemetryPacket] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._packets = list(packets)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._packets)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid():
            return None

        packet = self._packets[index.row()]
        column = index.column()
        value = self._raw_value(packet, column)

        if role == Qt.ItemDataRole.DisplayRole:
            return self._format_value(value, column)
        if role == Qt.ItemDataRole.UserRole:
            if isinstance(value, float) and not math.isfinite(value):
                return None
            return value
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column == 2:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ForegroundRole and column == 2:
            return QColor(STATE_COLORS[packet.track_state])
        return None

    @staticmethod
    def _raw_value(packet: TelemetryPacket, column: int) -> int | float | str:
        error_x, error_y = packet.error_px
        values: tuple[int | float | str, ...] = (
            packet.frame_id,
            packet.timestamp_s,
            packet.track_state.value,
            packet.fps,
            packet.loop_time_s * 1000.0,
            error_x,
            error_y,
            math.hypot(error_x, error_y),
            packet.error_az_rad * 1000.0,
            packet.error_el_rad * 1000.0,
            packet.lock_fraction * 100.0,
            packet.acquisition_time_s,
        )
        return values[column]

    @staticmethod
    def _format_value(value: int | float | str, column: int) -> str:
        if isinstance(value, float) and not math.isfinite(value):
            return "N/A"
        if column == 0:
            return f"{int(value):06d}"
        if column == 2:
            return str(value)
        precision = {1: 3, 3: 2, 4: 3, 8: 4, 9: 4, 10: 1, 11: 3}.get(column, 2)
        return f"{float(value):.{precision}f}"

    def set_packets(self, packets: Sequence[TelemetryPacket]) -> None:
        self.beginResetModel()
        self._packets = list(packets)
        self.endResetModel()

    def sync_packets(self, packets: Sequence[TelemetryPacket]) -> bool:
        """Append a growing live stream, resetting if a new session replaced it."""
        incoming_count = len(packets)
        current_count = len(self._packets)
        if incoming_count == current_count:
            if incoming_count == 0:
                return False
            old_last = self._packets[-1]
            new_last = packets[-1]
            if self._packet_key(old_last) == self._packet_key(new_last):
                return False
            self.set_packets(packets)
            return True

        can_append = incoming_count > current_count
        if can_append and current_count:
            old_last = self._packets[-1]
            matching_packet = packets[current_count - 1]
            can_append = self._packet_key(old_last) == self._packet_key(
                matching_packet
            )

        if can_append:
            self.beginInsertRows(QModelIndex(), current_count, incoming_count - 1)
            self._packets.extend(packets[current_count:])
            self.endInsertRows()
        else:
            self.set_packets(packets)
        return True

    @staticmethod
    def _packet_key(packet: TelemetryPacket) -> tuple[int, float | None]:
        timestamp = packet.timestamp_s
        return packet.frame_id, timestamp if math.isfinite(timestamp) else None


class SessionTrendChart(QWidget):
    """QPainter trend chart retaining the complete run rather than a rolling tail."""

    def __init__(
        self,
        title: str,
        line_color: str,
        unit: str,
        suggested_max: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.line_color = QColor(line_color)
        self.unit = unit
        self.suggested_max = suggested_max
        self._series: list[tuple[float, float]] = []
        self._finite_count = 0
        self._t_min = 0.0
        self._t_max = 0.0
        self._value_min = 0.0
        self._value_max = 0.0
        self._latest_value = 0.0
        self._render_cache_key: tuple[int, int] | None = None
        self._render_cache: list[tuple[float, float]] = []
        self.setMinimumSize(260, 185)

    def set_series(self, series: Iterable[tuple[float, float]]) -> None:
        self._series = list(series)
        self._recalculate_bounds()
        self._render_cache_key = None
        self.update()

    def extend_series(self, series: Iterable[tuple[float, float]]) -> None:
        additions = list(series)
        if not additions:
            return
        self._series.extend(additions)
        for timestamp, value in additions:
            self._include_in_bounds(timestamp, value)
        self._render_cache_key = None
        self.update()

    def _recalculate_bounds(self) -> None:
        self._finite_count = 0
        self._t_min = 0.0
        self._t_max = 0.0
        self._value_min = 0.0
        self._value_max = 0.0
        self._latest_value = 0.0
        for timestamp, value in self._series:
            self._include_in_bounds(timestamp, value)

    def _include_in_bounds(self, timestamp: float, value: float) -> None:
        if not math.isfinite(timestamp) or not math.isfinite(value):
            return
        if self._finite_count == 0:
            self._t_min = self._t_max = timestamp
            self._value_min = self._value_max = value
        else:
            self._t_min = min(self._t_min, timestamp)
            self._t_max = max(self._t_max, timestamp)
            self._value_min = min(self._value_min, value)
            self._value_max = max(self._value_max, value)
        self._finite_count += 1
        self._latest_value = value

    def _render_series(self, max_points: int) -> list[tuple[float, float]]:
        """Reduce long runs while retaining bucket extrema and missing-data gaps."""
        cache_key = (len(self._series), max_points)
        if cache_key == self._render_cache_key:
            return self._render_cache
        if len(self._series) <= max_points:
            rendered = list(self._series)
        else:
            bucket_count = max(1, max_points // 5)
            bucket_size = math.ceil(len(self._series) / bucket_count)
            rendered = []
            for start in range(0, len(self._series), bucket_size):
                bucket = self._series[start : start + bucket_size]
                finite_indexes = [
                    index
                    for index, (timestamp, value) in enumerate(bucket)
                    if math.isfinite(timestamp) and math.isfinite(value)
                ]
                chosen = {0, len(bucket) - 1}
                if finite_indexes:
                    chosen.add(
                        min(finite_indexes, key=lambda index: bucket[index][1])
                    )
                    chosen.add(
                        max(finite_indexes, key=lambda index: bucket[index][1])
                    )
                missing_index = next(
                    (
                        index
                        for index, (timestamp, value) in enumerate(bucket)
                        if not math.isfinite(timestamp) or not math.isfinite(value)
                    ),
                    None,
                )
                if missing_index is not None:
                    chosen.add(missing_index)
                rendered.extend(bucket[index] for index in sorted(chosen))
        self._render_cache_key = cache_key
        self._render_cache = rendered
        return rendered

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(0, 0, -1, -1)
        painter.fillRect(bounds, QColor(BG_INSET))
        painter.setPen(QPen(QColor(LINE), 1))
        painter.drawRect(bounds)

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(TEXT_1)))
        painter.drawText(QPointF(10, 17), self.title.upper())

        if self._finite_count == 0:
            painter.setFont(QFont("Consolas", 10))
            painter.setPen(QPen(QColor(TEXT_2)))
            painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, "NO SESSION DATA")
            return

        latest_text = f"{self._latest_value:.1f} {self.unit}"
        painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(TEXT_0)))
        latest_width = painter.fontMetrics().horizontalAdvance(latest_text)
        painter.drawText(QPointF(bounds.right() - latest_width - 10, 17), latest_text)

        plot = bounds.adjusted(43, 28, -10, -25)
        y_min = min(0.0, self._value_min)
        y_max = max(self.suggested_max, self._value_max)
        y_span = max(1e-9, y_max - y_min)
        t_min = self._t_min
        t_max = self._t_max
        t_span = max(1e-9, t_max - t_min)

        painter.setFont(QFont("Consolas", 7))
        for step in range(3):
            fraction = step / 2.0
            y = plot.bottom() - fraction * plot.height()
            painter.setPen(QPen(QColor(LINE), 0.5, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            label = f"{y_min + fraction * y_span:.1f}"
            painter.setPen(QPen(QColor(TEXT_2)))
            painter.drawText(QPointF(4, y + 3), label)

        painter.setPen(QPen(QColor(TEXT_2)))
        painter.drawText(QPointF(plot.left(), bounds.bottom() - 7), f"{t_min:.1f}s")
        end_label = f"{t_max:.1f}s"
        end_width = painter.fontMetrics().horizontalAdvance(end_label)
        painter.drawText(QPointF(plot.right() - end_width, bounds.bottom() - 7), end_label)

        max_points = max(10, int(plot.width() * 2))
        sampled = self._render_series(max_points)

        painter.setPen(QPen(self.line_color, 1.5))
        previous: QPointF | None = None
        for timestamp, value in sampled:
            if not math.isfinite(timestamp) or not math.isfinite(value):
                previous = None
                continue
            x = plot.left() + ((timestamp - t_min) / t_span) * plot.width()
            y = plot.bottom() - ((value - y_min) / y_span) * plot.height()
            point = QPointF(x, y)
            if previous is not None:
                painter.drawLine(previous, point)
            previous = point


class MetricCard(QFrame):
    """Compact metric tile with a stable label and monospace value."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(3)
        title_label = QLabel(title)
        title_label.setObjectName("telemetryLabel")
        self.value_label = QLabel("--")
        self.value_label.setObjectName("metricValue")
        self.value_label.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class AnalyticsWindow(QMainWindow):
    """Live analytics page for current telemetry and persisted performance logs."""

    live_json_exported = Signal(str)

    def __init__(
        self,
        live_logger: PerformanceLogger,
        log_directory: str | Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.live_logger = live_logger
        self.log_directory = Path(log_directory)
        self._display_logger = live_logger
        self._archive_logger: PerformanceLogger | None = None
        self._last_signature: tuple[int, int, int, float | None] | None = None
        self._chart_logger_id: int | None = None
        self._chart_packet_count = 0
        self._chart_last_key: tuple[int, float | None] | None = None

        self.setWindowTitle("FSOC Session Analytics and Performance Logs")
        self.setMinimumSize(1180, 760)
        self.resize(1360, 860)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        root = QWidget(self)
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        header = QFrame()
        header.setObjectName("raisedFrame")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 8, 14, 8)
        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        title = QLabel("SESSION ANALYTICS / PERFORMANCE LOGS")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        subtitle = QLabel("FULL-RUN TELEMETRY, TRACKING QUALITY, AND EXPORTABLE FRAME DATA")
        subtitle.setObjectName("telemetryLabel")
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        header_layout.addLayout(title_column)
        header_layout.addStretch()
        self.dataset_badge = QLabel("LIVE DATASET")
        self.dataset_badge.setObjectName("analyticsBadge")
        header_layout.addWidget(self.dataset_badge)
        root_layout.addWidget(header)

        toolbar = QFrame()
        toolbar.setObjectName("panelFrame")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)
        dataset_label = QLabel("DATASET")
        dataset_label.setObjectName("telemetryLabel")
        toolbar_layout.addWidget(dataset_label)
        self.dataset_combo = QComboBox()
        self.dataset_combo.setMinimumWidth(330)
        toolbar_layout.addWidget(self.dataset_combo)
        self.btn_refresh_runs = QPushButton("REFRESH RUNS")
        self.btn_open_log = QPushButton("OPEN LOG...")
        toolbar_layout.addWidget(self.btn_refresh_runs)
        toolbar_layout.addWidget(self.btn_open_log)
        toolbar_layout.addStretch()
        self.btn_export_json = QPushButton("EXPORT JSON")
        self.btn_export_csv = QPushButton("EXPORT CSV")
        toolbar_layout.addWidget(self.btn_export_json)
        toolbar_layout.addWidget(self.btn_export_csv)
        root_layout.addWidget(toolbar)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "OVERVIEW")
        self.tabs.addTab(self._build_frame_log_tab(), "FRAME LOG")
        root_layout.addWidget(self.tabs, stretch=1)

        self.status_label = QLabel("Current session telemetry is ready for analysis.")
        self.status_label.setObjectName("analyticsStatus")
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root_layout.addWidget(self.status_label)

        self.dataset_combo.currentIndexChanged.connect(self._on_dataset_changed)
        self.btn_refresh_runs.clicked.connect(self.refresh_saved_runs)
        self.btn_open_log.clicked.connect(self._choose_log)
        self.btn_export_json.clicked.connect(self._choose_json_export)
        self.btn_export_csv.clicked.connect(self._choose_csv_export)
        self.state_filter.currentTextChanged.connect(self._set_state_filter)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(500)
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start()

        self.refresh_saved_runs()
        self.refresh_data(force=True)

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(8)

        metric_grid = QGridLayout()
        metric_grid.setSpacing(8)
        metric_titles = (
            ("total_frames", "TOTAL FRAMES"),
            ("duration_s", "RUN DURATION"),
            ("average_fps", "AVERAGE FPS"),
            ("acquisition_time_s", "ACQUISITION TIME"),
            ("lock_retention_rate", "LOCK RETENTION"),
            ("mean_error_px", "MEAN ERROR"),
            ("rmse_error_px", "RMSE ERROR"),
            ("max_error_px", "MAX ERROR"),
        )
        self.metric_cards: dict[str, MetricCard] = {}
        for index, (key, title) in enumerate(metric_titles):
            card = MetricCard(title)
            self.metric_cards[key] = card
            metric_grid.addWidget(card, index // 4, index % 4)
        layout.addLayout(metric_grid)

        state_frame = QFrame()
        state_frame.setObjectName("panelFrame")
        state_layout = QHBoxLayout(state_frame)
        state_layout.setContentsMargins(12, 8, 12, 8)
        state_title = QLabel("STATE DISTRIBUTION")
        state_title.setObjectName("sectionHeader")
        state_layout.addWidget(state_title)
        self.state_labels: dict[TrackState, QLabel] = {}
        for state in TrackState:
            label = QLabel(f"{state.value}  0 / 0.0%")
            label.setObjectName("stateStat")
            label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            label.setStyleSheet(f"color: {STATE_COLORS[state]};")
            self.state_labels[state] = label
            state_layout.addWidget(label, stretch=1, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(state_frame)

        charts = QHBoxLayout()
        charts.setSpacing(8)
        self.chart_fps = SessionTrendChart("Full-run FPS", "#00E676", "FPS", 40.0)
        self.chart_error = SessionTrendChart("Tracking error magnitude", "#39C5CF", "px", 20.0)
        self.chart_lock = SessionTrendChart("Lock quality", "#B57CFF", "%", 100.0)
        charts.addWidget(self.chart_fps, stretch=1)
        charts.addWidget(self.chart_error, stretch=1)
        charts.addWidget(self.chart_lock, stretch=1)
        layout.addLayout(charts, stretch=1)
        return tab

    def _build_frame_log_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(8)

        controls = QHBoxLayout()
        filter_label = QLabel("TRACK STATE")
        filter_label.setObjectName("telemetryLabel")
        controls.addWidget(filter_label)
        self.state_filter = QComboBox()
        self.state_filter.addItem("ALL STATES")
        self.state_filter.addItems([state.value for state in TrackState])
        controls.addWidget(self.state_filter)
        controls.addStretch()
        self.row_count_label = QLabel("0 ROWS")
        self.row_count_label.setObjectName("monoNum")
        controls.addWidget(self.row_count_label)
        layout.addLayout(controls)

        self.table_model = TelemetryTableModel()
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setSortRole(Qt.ItemDataRole.UserRole)
        self.proxy_model.setFilterKeyColumn(2)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self.table = QTableView()
        self.table.setObjectName("analyticsTable")
        self.table.setModel(self.proxy_model)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, stretch=1)
        return tab

    def showEvent(self, event) -> None:
        if not self.refresh_timer.isActive():
            self.refresh_timer.start()
        self.refresh_saved_runs()
        self.refresh_data(force=True)
        super().showEvent(event)

    def closeEvent(self, event) -> None:
        self.refresh_timer.stop()
        super().closeEvent(event)

    def notify_session_reset(self) -> None:
        """Reset live views immediately when the telemetry source changes."""
        if self.dataset_combo.currentData() is None:
            self.table_model.set_packets(())
            self._last_signature = None
            self.refresh_data(force=True)

    def notify_log_saved(self, filepath: str | Path) -> None:
        self.refresh_saved_runs()
        self.status_label.setText(f"Performance log saved: {Path(filepath)}")

    def refresh_saved_runs(self) -> None:
        selected = self.dataset_combo.currentData()
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        self.dataset_combo.addItem("LIVE / CURRENT SESSION", None)

        candidates: list[Path] = []
        if self.log_directory.exists():
            candidates.extend(self.log_directory.glob("*.json"))
        if selected is not None:
            selected_path = Path(selected)
            if selected_path.is_file() and selected_path not in candidates:
                candidates.append(selected_path)
        legacy_log = Path.cwd() / "performance_log.json"
        if legacy_log.is_file() and legacy_log not in candidates:
            candidates.append(legacy_log)
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in candidates:
            modified = datetime.fromtimestamp(path.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            label = f"{path.stem}  /  {modified}"
            self.dataset_combo.addItem(label, str(path.resolve()))

        selected_index = self.dataset_combo.findData(selected)
        selection_was_removed = selected is not None and selected_index < 0
        self.dataset_combo.setCurrentIndex(max(0, selected_index))
        self.dataset_combo.blockSignals(False)
        if selected is not None:
            self._on_dataset_changed(0 if selection_was_removed else selected_index)

    def refresh_data(self, force: bool = False) -> None:
        logger = self._display_logger
        packets = logger.packets
        if packets:
            last = packets[-1]
            timestamp = last.timestamp_s if math.isfinite(last.timestamp_s) else None
            signature = (id(logger), len(packets), last.frame_id, timestamp)
        else:
            signature = (id(logger), 0, -1, -1.0)
        if not force and signature == self._last_signature:
            return
        self._last_signature = signature

        self.table_model.sync_packets(packets)
        self._update_summary(logger)
        self._update_state_distribution(packets)
        self._update_charts(packets)
        self.row_count_label.setText(
            f"{self.proxy_model.rowCount():,} / {len(packets):,} ROWS"
        )

    def _update_summary(self, logger: PerformanceLogger) -> None:
        summary = logger.compute_summary()
        self.metric_cards["total_frames"].set_value(f"{summary.total_frames:,}")
        self.metric_cards["duration_s"].set_value(
            self._format_metric(summary.duration_s, 2, "s")
        )
        self.metric_cards["average_fps"].set_value(
            self._format_metric(summary.average_fps, 2, "FPS")
        )
        acquisition = (
            f"{summary.acquisition_time_s:.3f} s"
            if math.isfinite(summary.acquisition_time_s)
            else "N/A"
        )
        self.metric_cards["acquisition_time_s"].set_value(acquisition)
        self.metric_cards["lock_retention_rate"].set_value(
            self._format_metric(summary.lock_retention_rate * 100.0, 1, "%", compact=True)
        )
        self.metric_cards["mean_error_px"].set_value(
            self._format_metric(summary.mean_error_px, 2, "px")
        )
        self.metric_cards["rmse_error_px"].set_value(
            self._format_metric(summary.rmse_error_px, 2, "px")
        )
        self.metric_cards["max_error_px"].set_value(
            self._format_metric(summary.max_error_px, 2, "px")
        )

    @staticmethod
    def _format_metric(
        value: float,
        precision: int,
        unit: str,
        compact: bool = False,
    ) -> str:
        if not math.isfinite(value):
            return "N/A"
        separator = "" if compact else " "
        return f"{value:.{precision}f}{separator}{unit}"

    def _update_state_distribution(self, packets: Sequence[TelemetryPacket]) -> None:
        total = len(packets)
        counts = {state: 0 for state in TrackState}
        for packet in packets:
            counts[packet.track_state] += 1
        for state, label in self.state_labels.items():
            count = counts[state]
            percentage = count * 100.0 / total if total else 0.0
            label.setText(f"{state.value}  {count:,} / {percentage:.1f}%")

    def _update_charts(self, packets: Sequence[TelemetryPacket]) -> None:
        logger_id = id(self._display_logger)
        packet_count = len(packets)
        can_append = logger_id == self._chart_logger_id and packet_count >= self._chart_packet_count
        if can_append and self._chart_packet_count:
            prior_packet = packets[self._chart_packet_count - 1]
            can_append = self._chart_last_key == (
                prior_packet.frame_id,
                prior_packet.timestamp_s
                if math.isfinite(prior_packet.timestamp_s)
                else None,
            )

        if can_append:
            new_packets = packets[self._chart_packet_count :]
            chart_method = "extend_series"
        else:
            new_packets = packets
            chart_method = "set_series"

        getattr(self.chart_fps, chart_method)(
            (packet.timestamp_s, packet.fps) for packet in new_packets
        )
        getattr(self.chart_error, chart_method)(
            (
                packet.timestamp_s,
                math.hypot(*packet.error_px)
                if all(math.isfinite(value) for value in packet.error_px)
                else float("nan"),
            )
            for packet in new_packets
        )
        getattr(self.chart_lock, chart_method)(
            (packet.timestamp_s, packet.lock_fraction * 100.0)
            for packet in new_packets
        )
        self._chart_logger_id = logger_id
        self._chart_packet_count = packet_count
        self._chart_last_key = (
            (
                packets[-1].frame_id,
                packets[-1].timestamp_s
                if math.isfinite(packets[-1].timestamp_s)
                else None,
            )
            if packets
            else None
        )

    def _set_state_filter(self, state: str) -> None:
        pattern = "" if state == "ALL STATES" else f"^{QRegularExpression.escape(state)}$"
        self.proxy_model.setFilterRegularExpression(QRegularExpression(pattern))
        self.row_count_label.setText(
            f"{self.proxy_model.rowCount():,} / {self.table_model.rowCount():,} ROWS"
        )

    def _on_dataset_changed(self, index: int) -> None:
        selected_path = self.dataset_combo.itemData(index)
        if selected_path is None:
            self._archive_logger = None
            self._display_logger = self.live_logger
            self.dataset_badge.setText("LIVE DATASET")
            self.status_label.setText("Displaying live telemetry from the current session.")
        else:
            try:
                self._archive_logger = load_performance_log(selected_path)
            except ValueError as exc:
                QMessageBox.warning(self, "Performance Log Error", str(exc))
                self.dataset_combo.setCurrentIndex(0)
                return
            self._display_logger = self._archive_logger
            self.dataset_badge.setText("ARCHIVED DATASET")
            self.status_label.setText(f"Displaying archived performance log: {selected_path}")
        self._last_signature = None
        self.table_model.set_packets(self._display_logger.packets)
        self.refresh_data(force=True)

    def _choose_log(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open FSOC Performance Log",
            str(self.log_directory),
            "JSON Performance Logs (*.json)",
        )
        if not filepath:
            return
        absolute_path = str(Path(filepath).resolve())
        index = self.dataset_combo.findData(absolute_path)
        if index < 0:
            self.dataset_combo.addItem(Path(filepath).stem, absolute_path)
            index = self.dataset_combo.count() - 1
        self.dataset_combo.setCurrentIndex(index)

    @property
    def displayed_logger(self) -> PerformanceLogger:
        return self._display_logger

    def export_json_to(self, filepath: str | Path) -> Path:
        path = Path(filepath)
        self._display_logger.export_json(path)
        self.status_label.setText(f"JSON dataset exported: {path}")
        if self._display_logger is self.live_logger:
            self.live_json_exported.emit(str(path))
        return path

    def export_csv_to(self, filepath: str | Path) -> Path:
        path = Path(filepath)
        self._display_logger.export_csv(path)
        self.status_label.setText(f"CSV dataset exported: {path}")
        return path

    def _choose_json_export(self) -> None:
        self._choose_export("JSON Performance Log (*.json)", ".json", self.export_json_to)

    def _choose_csv_export(self) -> None:
        self._choose_export("CSV Frame Data (*.csv)", ".csv", self.export_csv_to)

    def _choose_export(
        self,
        file_filter: str,
        suffix: str,
        exporter: Callable[[Path], Path],
    ) -> None:
        self.log_directory.mkdir(parents=True, exist_ok=True)
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Analytics Dataset",
            str(self.log_directory / f"fsoc_analytics{suffix}"),
            file_filter,
        )
        if not filepath:
            return
        path = Path(filepath)
        if path.suffix.lower() != suffix:
            path = path.with_suffix(suffix)
        try:
            exporter(path)
        except OSError as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
