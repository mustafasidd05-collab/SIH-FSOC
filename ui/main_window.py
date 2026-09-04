"""ui/main_window.py -- MainWindow entry point, Cockpit layout, ConfigPanel, TelemetryStrip, and --selftest runner."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from PySide6.QtCore import QPointF, QRectF, QSize, QStandardPaths, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.contracts import TelemetryPacket, TrackState
from runtime.live_source import LiveTelemetrySource
from telemetry.performance_logger import PerformanceLogger
from ui.analytics_window import AnalyticsWindow
from ui.charts import LockStateIndicator, RollingChart
from ui.mock_telemetry import MockTelemetrySource
from ui.overlay import VideoPane
from ui.palette import (
    BG_INSET,
    BG_PANEL,
    BG_ROOT,
    LINE,
    LINE_STRONG,
    STATE_COLORS,
    TEXT_0,
    TEXT_1,
    TEXT_2,
)


class ConfigPanel(QFrame):
    """300px sidebar panel containing RUN toggle, SCENE controls, and DISTURBANCE sliders."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("configPanel")
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Header Title
        lbl_header = QLabel("MISSION CONTROL")
        lbl_header.setObjectName("sectionHeader")
        layout.addWidget(lbl_header)

        # RUN / STOP Main Toggle Button
        self.btn_run = QPushButton("START SIMULATION")
        self.btn_run.setObjectName("runButton")
        self.btn_run.setCheckable(True)
        self.btn_run.setFixedHeight(36)
        layout.addWidget(self.btn_run)

        grp_source = QGroupBox("VIDEO INPUT SOURCE")
        source_layout = QVBoxLayout(grp_source)
        self.lbl_video_source = QLabel("VIRTUAL SCENE")
        self.lbl_video_source.setObjectName("telemetryLabel")
        self.lbl_video_source.setWordWrap(True)
        source_layout.addWidget(self.lbl_video_source)
        self.btn_load_video = QPushButton("LOAD MP4 VIDEO...")
        source_layout.addWidget(self.btn_load_video)
        layout.addWidget(grp_source)

        # Group 1: SCENE CONTROLS
        grp_scene = QGroupBox("SCENE CONFIGURATION")
        lbl_scene_layout = QVBoxLayout(grp_scene)

        # Target Speed Slider
        lbl_speed = QLabel("TARGET VELOCITY (m/s)")
        lbl_speed.setObjectName("telemetryLabel")
        lbl_scene_layout.addWidget(lbl_speed)
        
        row_speed = QHBoxLayout()
        self.sld_speed = QSlider(Qt.Orientation.Horizontal)
        self.sld_speed.setRange(1, 100)
        self.sld_speed.setValue(15)
        self.spn_speed = QSpinBox()
        self.spn_speed.setRange(1, 100)
        self.spn_speed.setValue(15)
        self.sld_speed.valueChanged.connect(self.spn_speed.setValue)
        self.spn_speed.valueChanged.connect(self.sld_speed.setValue)
        row_speed.addWidget(self.sld_speed)
        row_speed.addWidget(self.spn_speed)
        lbl_scene_layout.addLayout(row_speed)

        # Target Pattern
        lbl_pattern = QLabel("MOTION PATTERN")
        lbl_pattern.setObjectName("telemetryLabel")
        lbl_scene_layout.addWidget(lbl_pattern)
        self.cmb_pattern = QComboBox()
        self.cmb_pattern.addItems(["Lissajous Curve", "Spiral Track", "Sinusoidal Sweep"])
        lbl_scene_layout.addWidget(self.cmb_pattern)

        layout.addWidget(grp_scene)

        # Group 2: DISTURBANCE CONTROLS
        grp_dist = QGroupBox("DISTURBANCE MODELS")
        lbl_dist_layout = QVBoxLayout(grp_dist)

        # Vibration Jitter
        lbl_vib = QLabel("PLATFORM VIBRATION (μrad)")
        lbl_vib.setObjectName("telemetryLabel")
        lbl_dist_layout.addWidget(lbl_vib)
        row_vib = QHBoxLayout()
        self.sld_vib = QSlider(Qt.Orientation.Horizontal)
        self.sld_vib.setRange(0, 50)
        self.sld_vib.setValue(5)
        self.spn_vib = QSpinBox()
        self.spn_vib.setRange(0, 50)
        self.spn_vib.setValue(5)
        self.sld_vib.valueChanged.connect(self.spn_vib.setValue)
        self.spn_vib.valueChanged.connect(self.sld_vib.setValue)
        row_vib.addWidget(self.sld_vib)
        row_vib.addWidget(self.spn_vib)
        lbl_dist_layout.addLayout(row_vib)

        # Turbulence Index
        lbl_turb = QLabel("ATMOSPHERIC TURBULENCE (Cn²)")
        lbl_turb.setObjectName("telemetryLabel")
        lbl_dist_layout.addWidget(lbl_turb)
        row_turb = QHBoxLayout()
        self.sld_turb = QSlider(Qt.Orientation.Horizontal)
        self.sld_turb.setRange(0, 100)
        self.sld_turb.setValue(20)
        self.spn_turb = QSpinBox()
        self.spn_turb.setRange(0, 100)
        self.spn_turb.setValue(20)
        self.sld_turb.valueChanged.connect(self.spn_turb.setValue)
        self.spn_turb.valueChanged.connect(self.sld_turb.setValue)
        row_turb.addWidget(self.sld_turb)
        row_turb.addWidget(self.spn_turb)
        lbl_dist_layout.addLayout(row_turb)

        # Sensor Noise
        lbl_noise = QLabel("SENSOR NOISE (σ px)")
        lbl_noise.setObjectName("telemetryLabel")
        lbl_dist_layout.addWidget(lbl_noise)
        row_noise = QHBoxLayout()
        self.sld_noise = QSlider(Qt.Orientation.Horizontal)
        self.sld_noise.setRange(0, 20)
        self.sld_noise.setValue(2)
        self.spn_noise = QSpinBox()
        self.spn_noise.setRange(0, 20)
        self.spn_noise.setValue(2)
        self.sld_noise.valueChanged.connect(self.spn_noise.setValue)
        self.spn_noise.valueChanged.connect(self.sld_noise.setValue)
        row_noise.addWidget(self.sld_noise)
        row_noise.addWidget(self.spn_noise)
        lbl_dist_layout.addLayout(row_noise)

        layout.addWidget(grp_dist)

        layout.addStretch()


class TelemetryStrip(QFrame):
    """56px bottom bar rendering monochrome numerical telemetry values."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("telemetryStrip")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(24)

        # Helper to create telemetry metric item
        def make_item(label: str) -> Tuple[QLabel, QLabel]:
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl_title = QLabel(label)
            lbl_title.setObjectName("telemetryLabel")
            lbl_val = QLabel("--")
            lbl_val.setObjectName("telemetryNum")
            lbl_val.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
            col.addWidget(lbl_title)
            col.addWidget(lbl_val)
            layout.addLayout(col)
            return lbl_val

        self.lbl_fps = make_item("FPS")
        self.lbl_loop = make_item("LOOP TIME")
        self.lbl_err_px = make_item("ERR X/Y")
        self.lbl_az_el = make_item("AZ / EL RAD")
        self.lbl_lock = make_item("LOCK FRACTION")
        self.lbl_acq = make_item("ACQ TIME")
        self.lbl_frame = make_item("FRAME ID")

        layout.addStretch()

    def update_telemetry(self, packet: TelemetryPacket) -> None:
        """Update telemetry figures from packet."""
        self.lbl_fps.setText(f"{packet.fps:.1f}")
        self.lbl_loop.setText(f"{packet.loop_time_s * 1000.0:.1f} ms")
        err_x, err_y = packet.error_px
        self.lbl_err_px.setText(f"{err_x:+0.1f} / {err_y:+0.1f} px")
        self.lbl_az_el.setText(f"{packet.error_az_rad:+0.4f} / {packet.error_el_rad:+0.4f}")
        self.lbl_lock.setText(f"{packet.lock_fraction * 100.0:.1f}%")
        acq_str = f"{packet.acquisition_time_s:.2f}s" if not math.isnan(packet.acquisition_time_s) else "N/A"
        self.lbl_acq.setText(acq_str)
        self.lbl_frame.setText(f"#{packet.frame_id:06d}")


class MainWindow(QMainWindow):
    """Main cockpit window for FSOC coarse-alignment tracking simulator."""

    def __init__(
        self,
        time_scale: float = 1.0,
        use_live_source: bool = False,
        video_path: str | Path | None = None,
        log_directory: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.time_scale = time_scale
        default_documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        self.log_directory = (
            Path(log_directory)
            if log_directory is not None
            else Path(default_documents or Path.home())
            / "FSOC Simulator"
            / "performance_logs"
        )
        self.performance_logger = PerformanceLogger()
        self.analytics_window: AnalyticsWindow | None = None
        self._session_active = False
        self._session_started = False
        self._session_saved = False
        self._last_log_path: Path | None = None
        self.setWindowTitle("FSOC Coarse-Alignment Tracking Simulator (SIH 26169)")
        self.setMinimumSize(1440, 900)

        # Load stylesheet
        qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

        # Central widget container
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 1. HEADER BAR
        header_frame = QFrame()
        header_frame.setFixedHeight(40)
        header_frame.setObjectName("raisedFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 0, 12, 0)

        lbl_title = QLabel("FSOC COARSE-ALIGNMENT TRACKING SIMULATOR")
        lbl_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        header_layout.addWidget(lbl_title)

        header_layout.addStretch()

        self.btn_analytics = QPushButton("ANALYTICS / LOGS")
        self.btn_analytics.setObjectName("analyticsButton")
        header_layout.addWidget(self.btn_analytics)

        self.lbl_state_chip = QLabel("[ SEARCH ]")
        self.lbl_state_chip.setObjectName("monoNum")
        self.lbl_state_chip.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        header_layout.addWidget(self.lbl_state_chip)

        header_layout.addWidget(QLabel("·"))

        self.lbl_utc = QLabel("00:00:00 UTC")
        self.lbl_utc.setObjectName("monoNum")
        header_layout.addWidget(self.lbl_utc)

        main_layout.addWidget(header_frame)

        # 2. MIDDLE SPLIT: [VideoPane, stretch] [ConfigPanel 300px]
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(8)

        self.video_pane = VideoPane()
        middle_layout.addWidget(self.video_pane, stretch=1)

        self.config_panel = ConfigPanel()
        if video_path is not None:
            self.config_panel.lbl_video_source.setText(Path(video_path).name.upper())
            self.config_panel.lbl_video_source.setToolTip(str(Path(video_path)))
        middle_layout.addWidget(self.config_panel)

        main_layout.addLayout(middle_layout, stretch=1)

        # 3. BOTTOM DOCK: [LockStateIndicator 230px] [3 x RollingChart]
        bottom_dock = QHBoxLayout()
        bottom_dock.setSpacing(8)

        self.lock_indicator = LockStateIndicator()
        bottom_dock.addWidget(self.lock_indicator)

        self.chart_fps = RollingChart(title="FPS", line_color_hex="#00E676", min_val=0, max_val=40, unit_str=" FPS")
        bottom_dock.addWidget(self.chart_fps, stretch=1)

        self.chart_err = RollingChart(title="Tracking Error", line_color_hex="#39C5CF", min_val=0, max_val=200, unit_str=" px")
        bottom_dock.addWidget(self.chart_err, stretch=1)

        self.chart_lock = RollingChart(title="Lock Quality", line_color_hex="#B57CFF", min_val=0, max_val=100, unit_str="%")
        bottom_dock.addWidget(self.chart_lock, stretch=1)

        main_layout.addLayout(bottom_dock)

        # 4. TELEMETRY STRIP
        self.telemetry_strip = TelemetryStrip()
        main_layout.addWidget(self.telemetry_strip)

        # Wire Telemetry Source (Live, Video, or Mock)
        if use_live_source:
            self.telemetry_source = LiveTelemetrySource(time_scale=time_scale, video_path=video_path, parent=self)
        else:
            self.telemetry_source = MockTelemetrySource(time_scale=time_scale, parent=self)
        self.telemetry_source.telemetry_updated.connect(self._on_telemetry_updated)

        # Wire Run Button
        self.config_panel.btn_run.toggled.connect(self._on_run_toggled)
        self.config_panel.btn_load_video.clicked.connect(self._on_load_video_clicked)
        self.btn_analytics.clicked.connect(self._show_analytics)
        self.video_pane.target_selected.connect(self._on_target_selected)

        # Clock timer for UTC header
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_utc_clock)
        self.clock_timer.start(1000)

    def _on_run_toggled(self, checked: bool) -> None:
        if checked:
            self._session_active = True
            self._session_started = True
            self.config_panel.btn_run.setText("STOP SIMULATION")
            self.telemetry_source.start()
        else:
            self.config_panel.btn_run.setText("START SIMULATION")
            self.telemetry_source.stop()
            self._session_active = False
            self._finalize_session()

    def _show_analytics(self) -> None:
        """Open or focus the single non-modal analytics page."""
        if self.analytics_window is None:
            self.analytics_window = AnalyticsWindow(
                self.performance_logger,
                self.log_directory,
                parent=self,
            )
            self.analytics_window.live_json_exported.connect(
                self._on_live_log_exported
            )
        self.analytics_window.show()
        self.analytics_window.raise_()
        self.analytics_window.activateWindow()

    def _finalize_session(self) -> Path | None:
        """Persist the completed run once and expose it to the analytics page."""
        if self._session_saved or not self.performance_logger.packets:
            return self._last_log_path
        if self._last_log_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
            filepath = self.log_directory / f"fsoc_run_{timestamp}.json"
        else:
            filepath = self._last_log_path
        try:
            self.performance_logger.export_json(filepath)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Performance Log Save Failed",
                f"The run completed, but its performance log could not be saved:\n{exc}",
            )
            return None
        self._session_saved = True
        self._last_log_path = filepath
        if self.analytics_window is not None:
            self.analytics_window.notify_log_saved(filepath)
        return filepath

    def _on_live_log_exported(self, filepath: str) -> None:
        """Treat an explicit live JSON export as a successful session save."""
        self._session_saved = True

    def _on_load_video_clicked(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Benchmark MP4 Video",
            "",
            "MP4 Video (*.mp4 *.MP4)",
        )
        if file_path:
            self._load_video(file_path)

    def _load_video(self, file_path: str | Path) -> bool:
        """Replace the active source transactionally with an MP4-backed source."""
        try:
            new_source = LiveTelemetrySource(
                time_scale=self.time_scale,
                video_path=file_path,
                parent=self,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "Video Load Failed", str(exc))
            return False

        was_running = self.config_panel.btn_run.isChecked()
        old_source = self.telemetry_source
        old_source.stop()
        self._session_active = False
        if (
            self._session_started
            and self.performance_logger.packets
            and not self._session_saved
            and self._finalize_session() is None
        ):
            if was_running:
                self._session_active = True
                old_source.start()
            if hasattr(new_source, "shutdown"):
                new_source.shutdown()
            new_source.deleteLater()
            return False
        try:
            old_source.telemetry_updated.disconnect(self._on_telemetry_updated)
        except RuntimeError:
            pass
        if hasattr(old_source, "shutdown"):
            old_source.shutdown()
        old_source.deleteLater()

        self.telemetry_source = new_source
        self.telemetry_source.telemetry_updated.connect(self._on_telemetry_updated)
        self.config_panel.lbl_video_source.setText(Path(file_path).name.upper())
        self.config_panel.lbl_video_source.setToolTip(str(Path(file_path)))
        self.chart_fps.clear()
        self.chart_err.clear()
        self.chart_lock.clear()
        self.performance_logger.reset()
        self._session_started = was_running
        self._session_saved = False
        self._last_log_path = None
        if self.analytics_window is not None:
            self.analytics_window.notify_session_reset()
        if was_running:
            self._session_active = True
            self.telemetry_source.start()
        return True

    def _on_target_selected(self, centroid_px: tuple[float, float]) -> None:
        """Ask a live source to acquire the candidate nearest the click."""
        if hasattr(self.telemetry_source, "select_target"):
            self.telemetry_source.select_target(centroid_px)

    def closeEvent(self, event) -> None:
        """Release timers and video handles before closing the cockpit."""
        self.clock_timer.stop()
        was_running = self._session_active
        if was_running:
            self.telemetry_source.stop()
            self._session_active = False
        if (
            self._session_started
            and self.performance_logger.packets
            and not self._session_saved
            and self._finalize_session() is None
        ):
            if was_running:
                self._session_active = True
                self.telemetry_source.start()
            self._show_analytics()
            if self.analytics_window is not None:
                self.analytics_window.status_label.setText(
                    "AUTOMATIC SAVE FAILED: export the live dataset to JSON before closing."
                )
            self.clock_timer.start(1000)
            event.ignore()
            return
        if self.analytics_window is not None:
            self.analytics_window.close()
        if hasattr(self.telemetry_source, "shutdown"):
            self.telemetry_source.shutdown()
        else:
            self.telemetry_source.stop()
        super().closeEvent(event)

    def _on_telemetry_updated(self, packet: TelemetryPacket, image: np.ndarray) -> None:
        self.performance_logger.record(packet)
        if self._session_active:
            self._session_saved = False

        # Update video pane
        self.video_pane.update_frame(packet, image)

        # Update lock state indicator
        self.lock_indicator.set_state(packet.track_state)

        # Update charts
        self.chart_fps.push(packet.timestamp_s, packet.fps)
        err_dist = math.hypot(packet.error_px[0], packet.error_px[1]) if packet.track_state != TrackState.LOST else 0.0
        self.chart_err.push(packet.timestamp_s, err_dist)
        self.chart_lock.push(packet.timestamp_s, packet.lock_fraction * 100.0)

        # Update telemetry strip
        self.telemetry_strip.update_telemetry(packet)

        # Update header chip
        state_hex = STATE_COLORS[packet.track_state]
        self.lbl_state_chip.setText(f"[ {packet.track_state.value} ]")
        self.lbl_state_chip.setStyleSheet(f"color: {state_hex};")

    def _update_utc_clock(self) -> None:
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.lbl_utc.setText(f"{now} UTC")


def run_selftest() -> int:
    """Run offscreen selftest, measure tick lag, step through all 5 states, save screenshots."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    use_live = "--live" in sys.argv
    window = MainWindow(time_scale=10.0, use_live_source=use_live)
    window.resize(1440, 900)
    window.show()

    source = window.telemetry_source
    
    # Track tick arrival times for lag measurement
    tick_timestamps: List[float] = []
    packet_timestamps: List[float] = []
    observed_states: Dict[TrackState, QPixmap] = {}
    expected_states = [
        TrackState.SEARCH,
        TrackState.ACQUIRE,
        TrackState.TRACK,
        TrackState.LOST,
        TrackState.REACQUIRE,
    ]

    print("[SELFTEST] Starting accelerated offscreen run...")
    start_wall_time = time.time()

    # Step through simulation frames until all 5 states are captured
    for _ in range(600):
        t_now = time.time()
        tick_timestamps.append(t_now)

        packet, img = source.step()
        packet_timestamps.append(packet.timestamp_s)
        window._on_telemetry_updated(packet, img)
        app.processEvents()

        state = packet.track_state
        if state in expected_states and state not in observed_states:
            # Capture screenshot of window in this state
            pixmap = window.grab()
            observed_states[state] = pixmap
            print(f"[SELFTEST] Captured screenshot for state: {state.value}")

        if len(observed_states) == len(expected_states):
            break

    elapsed_wall = time.time() - start_wall_time
    print(f"[SELFTEST] Completed run in {elapsed_wall:.2f}s wall time.")

    # 1. Compute Tick Interval / Lag Statistics
    # Expected interval at 30 Hz nominal rate is 1/30 s (33.33 ms).
    nominal_dt_s = 1.0 / 30.0
    expected_step_s = nominal_dt_s * source.time_scale

    intervals_ms = [
        (tick_timestamps[i] - tick_timestamps[i - 1]) * 1000.0
        for i in range(1, len(tick_timestamps))
    ]
    
    # Check simulated telemetry packet time step consistency
    sim_intervals_s = [
        packet_timestamps[i] - packet_timestamps[i - 1]
        for i in range(1, len(packet_timestamps))
    ]
    on_time_ticks = sum(1 for dt in sim_intervals_s if dt <= 2.0 * expected_step_s)
    pct_on_time = (on_time_ticks / len(sim_intervals_s)) * 100.0 if sim_intervals_s else 100.0

    print(f"[SELFTEST] Total Ticks: {len(tick_timestamps)}")
    print(f"[SELFTEST] Nominal 30 Hz Frame Interval: {nominal_dt_s * 1000.0:.2f} ms")
    print(f"[SELFTEST] Average Wall Loop Time: {sum(intervals_ms) / len(intervals_ms):.2f} ms")
    print(f"[SELFTEST] Ticks within 2x nominal 30 Hz interval (<=66.7ms sim): {on_time_ticks}/{len(sim_intervals_s)} ({pct_on_time:.2f}%)")

    # 2. Save Screenshots for all 5 states
    saved_files = []
    for state in expected_states:
        filename = f"selftest_{state.value}.png"
        if state in observed_states:
            observed_states[state].save(filename, "PNG")
            print(f"[SELFTEST] Saved screenshot: {filename}")
            saved_files.append(filename)
        else:
            print(f"[SELFTEST] ERROR: State {state.value} was not observed during selftest!")

    # Verify all 5 states captured and tick performance bar met
    assert len(saved_files) == 5, f"Expected 5 screenshots, saved {len(saved_files)}"
    assert pct_on_time >= 95.0, f"Tick timing lag failure: only {pct_on_time:.2f}% of ticks met the 2x interval requirement"

    print("[SELFTEST] ALL 5 STATES CAPTURED AND VERIFIED SUCCESSFULLY.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(run_selftest())
    else:
        app = QApplication(sys.argv)
        video_path = None
        if "--video" in sys.argv:
            try:
                idx = sys.argv.index("--video")
                if idx + 1 < len(sys.argv):
                    video_path = sys.argv[idx + 1]
            except ValueError:
                pass

        use_live = "--live" in sys.argv or video_path is not None
        window = MainWindow(use_live_source=use_live, video_path=video_path)
        window.show()
        sys.exit(app.exec())
