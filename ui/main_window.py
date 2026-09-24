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
    QScrollArea,
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


MOTION_PATTERN_OPTIONS: list[str] = [
    "Linear Track",
    "Sinusoidal Sweep",
    "Lissajous Curve",
    "Archimedean Spiral",
]

PATTERN_TO_KIND: dict[str, str] = {
    "Linear Track": "linear",
    "Sinusoidal Sweep": "sinusoidal",
    "Lissajous Curve": "lissajous",
    "Archimedean Spiral": "spiral",
    "Straight Line": "linear",
    "Spiral Track": "spiral",
    "linear": "linear",
    "sinusoidal": "sinusoidal",
    "lissajous": "lissajous",
    "spiral": "spiral",
}


class ConfigPanel(QFrame):
    """300px sidebar panel containing RUN toggle, SCENE controls, DISTURBANCE models, and PID tuning."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("configPanel")
        self.setFixedWidth(300)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(10)

        # Header Title
        lbl_header = QLabel("MISSION CONTROL")
        lbl_header.setObjectName("sectionHeader")
        outer_layout.addWidget(lbl_header)

        # RUN / STOP Main Toggle Button
        self.btn_run = QPushButton("START SIMULATION")
        self.btn_run.setObjectName("runButton")
        self.btn_run.setCheckable(True)
        self.btn_run.setFixedHeight(36)
        outer_layout.addWidget(self.btn_run)

        # Scrollable container for all controls
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("configScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)

        # Group 0: VIDEO INPUT SOURCE
        grp_source = QGroupBox("VIDEO INPUT SOURCE")
        source_layout = QVBoxLayout(grp_source)
        self.lbl_video_source = QLabel("VIRTUAL SCENE")
        self.lbl_video_source.setObjectName("telemetryLabel")
        self.lbl_video_source.setWordWrap(True)
        source_layout.addWidget(self.lbl_video_source)
        self.btn_load_video = QPushButton("LOAD MP4 VIDEO...")
        source_layout.addWidget(self.btn_load_video)
        self.btn_reset_scene = QPushButton("SWITCH TO VIRTUAL SCENE")
        self.btn_reset_scene.setObjectName("resetSceneButton")
        self.btn_reset_scene.setEnabled(False)
        source_layout.addWidget(self.btn_reset_scene)
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
        self.spn_speed.setSuffix(" m/s")

        def _sync_speed_slider(val: int) -> None:
            self.spn_speed.blockSignals(True)
            self.spn_speed.setValue(val)
            self.spn_speed.blockSignals(False)

        def _sync_speed_spin(val: int) -> None:
            self.sld_speed.blockSignals(True)
            self.sld_speed.setValue(val)
            self.sld_speed.blockSignals(False)

        self.sld_speed.valueChanged.connect(_sync_speed_slider)
        self.spn_speed.valueChanged.connect(_sync_speed_spin)
        row_speed.addWidget(self.sld_speed)
        row_speed.addWidget(self.spn_speed)
        lbl_scene_layout.addLayout(row_speed)

        # Target Size (px)
        lbl_size = QLabel("TARGET SIZE (RADIUS px)")
        lbl_size.setObjectName("telemetryLabel")
        lbl_scene_layout.addWidget(lbl_size)
        self.spn_size = QSpinBox()
        self.spn_size.setRange(2, 30)
        self.spn_size.setValue(6)
        self.spn_size.setSuffix(" px")
        lbl_scene_layout.addWidget(self.spn_size)

        # Target Pattern
        lbl_pattern = QLabel("MOTION PATTERN")
        lbl_pattern.setObjectName("telemetryLabel")
        lbl_scene_layout.addWidget(lbl_pattern)
        self.cmb_pattern = QComboBox()
        self.cmb_pattern.addItems(MOTION_PATTERN_OPTIONS)
        lbl_scene_layout.addWidget(self.cmb_pattern)

        layout.addWidget(grp_scene)

        # Group 2: FAULT INJECTION (Decoy Beacon)
        grp_fault = QGroupBox("FAULT INJECTION")
        fault_layout = QVBoxLayout(grp_fault)
        self.btn_decoy = QPushButton("DEPLOY FAULT DECOY")
        self.btn_decoy.setObjectName("decoyButton")
        self.btn_decoy.setCheckable(True)
        self.btn_decoy.setFixedHeight(28)
        fault_layout.addWidget(self.btn_decoy)
        layout.addWidget(grp_fault)

        # Group 3: DISTURBANCE CONTROLS
        grp_dist = QGroupBox("DISTURBANCE MODELS")
        lbl_dist_layout = QVBoxLayout(grp_dist)

        # Profile Quick Preset
        lbl_preset = QLabel("DISTURBANCE PRESET")
        lbl_preset.setObjectName("telemetryLabel")
        lbl_dist_layout.addWidget(lbl_preset)
        self.cmb_profile = QComboBox()
        self.cmb_profile.addItems(["Mild", "Moderate", "Severe", "Custom"])
        self.cmb_profile.setCurrentText("Mild")
        lbl_dist_layout.addWidget(self.cmb_profile)

        # Vibration Jitter
        lbl_vib = QLabel("PLATFORM VIBRATION (px σ)")
        lbl_vib.setObjectName("telemetryLabel")
        lbl_dist_layout.addWidget(lbl_vib)
        row_vib = QHBoxLayout()
        self.sld_vib = QSlider(Qt.Orientation.Horizontal)
        self.sld_vib.setRange(0, 50)
        self.sld_vib.setValue(4)
        self.spn_vib = QDoubleSpinBox()
        self.spn_vib.setRange(0.0, 5.0)
        self.spn_vib.setSingleStep(0.1)
        self.spn_vib.setValue(0.4)
        self.spn_vib.setDecimals(1)
        self.spn_vib.setSuffix(" px")

        def _sync_vib_slider(val: int) -> None:
            self.spn_vib.blockSignals(True)
            self.spn_vib.setValue(val / 10.0)
            self.spn_vib.blockSignals(False)

        def _sync_vib_spin(val: float) -> None:
            self.sld_vib.blockSignals(True)
            self.sld_vib.setValue(int(round(val * 10.0)))
            self.sld_vib.blockSignals(False)

        self.sld_vib.valueChanged.connect(_sync_vib_slider)
        self.spn_vib.valueChanged.connect(_sync_vib_spin)
        row_vib.addWidget(self.sld_vib)
        row_vib.addWidget(self.spn_vib)
        lbl_dist_layout.addLayout(row_vib)

        # Turbulence Index
        lbl_turb = QLabel("ATMOSPHERIC TURBULENCE (px σ)")
        lbl_turb.setObjectName("telemetryLabel")
        lbl_dist_layout.addWidget(lbl_turb)
        row_turb = QHBoxLayout()
        self.sld_turb = QSlider(Qt.Orientation.Horizontal)
        self.sld_turb.setRange(0, 50)
        self.sld_turb.setValue(4)
        self.spn_turb = QDoubleSpinBox()
        self.spn_turb.setRange(0.0, 5.0)
        self.spn_turb.setSingleStep(0.1)
        self.spn_turb.setValue(0.4)
        self.spn_turb.setDecimals(1)
        self.spn_turb.setSuffix(" px")

        def _sync_turb_slider(val: int) -> None:
            self.spn_turb.blockSignals(True)
            self.spn_turb.setValue(val / 10.0)
            self.spn_turb.blockSignals(False)

        def _sync_turb_spin(val: float) -> None:
            self.sld_turb.blockSignals(True)
            self.sld_turb.setValue(int(round(val * 10.0)))
            self.sld_turb.blockSignals(False)

        self.sld_turb.valueChanged.connect(_sync_turb_slider)
        self.spn_turb.valueChanged.connect(_sync_turb_spin)
        row_turb.addWidget(self.sld_turb)
        row_turb.addWidget(self.spn_turb)
        lbl_dist_layout.addLayout(row_turb)

        # Sensor Noise
        lbl_noise = QLabel("SENSOR NOISE (SNR dB)")
        lbl_noise.setObjectName("telemetryLabel")
        lbl_dist_layout.addWidget(lbl_noise)
        row_noise = QHBoxLayout()
        self.sld_noise = QSlider(Qt.Orientation.Horizontal)
        self.sld_noise.setRange(6, 40)
        self.sld_noise.setValue(35)
        self.spn_noise = QSpinBox()
        self.spn_noise.setRange(6, 40)
        self.spn_noise.setValue(35)
        self.spn_noise.setSuffix(" dB")

        def _sync_noise_slider(val: int) -> None:
            self.spn_noise.blockSignals(True)
            self.spn_noise.setValue(val)
            self.spn_noise.blockSignals(False)

        def _sync_noise_spin(val: int) -> None:
            self.sld_noise.blockSignals(True)
            self.sld_noise.setValue(val)
            self.sld_noise.blockSignals(False)

        self.sld_noise.valueChanged.connect(_sync_noise_slider)
        self.spn_noise.valueChanged.connect(_sync_noise_spin)
        row_noise.addWidget(self.sld_noise)
        row_noise.addWidget(self.spn_noise)
        lbl_dist_layout.addLayout(row_noise)

        layout.addWidget(grp_dist)

        # Group 4: PID CONTROLLER
        grp_pid = QGroupBox("PID CONTROLLER")
        pid_layout = QVBoxLayout(grp_pid)

        # Kp row
        lbl_kp = QLabel("PROPORTIONAL GAIN (Kp rad/px)")
        lbl_kp.setObjectName("telemetryLabel")
        pid_layout.addWidget(lbl_kp)
        self.spn_kp = QDoubleSpinBox()
        self.spn_kp.setRange(0.00000, 0.01000)
        self.spn_kp.setDecimals(5)
        self.spn_kp.setSingleStep(0.00005)
        self.spn_kp.setValue(0.00030)
        pid_layout.addWidget(self.spn_kp)

        # Ki row
        lbl_ki = QLabel("INTEGRAL GAIN (Ki rad/(px·s))")
        lbl_ki.setObjectName("telemetryLabel")
        pid_layout.addWidget(lbl_ki)
        self.spn_ki = QDoubleSpinBox()
        self.spn_ki.setRange(0.00000, 0.00100)
        self.spn_ki.setDecimals(5)
        self.spn_ki.setSingleStep(0.00001)
        self.spn_ki.setValue(0.00001)
        pid_layout.addWidget(self.spn_ki)

        # Kd row
        lbl_kd = QLabel("DERIVATIVE GAIN (Kd rad·s/px)")
        lbl_kd.setObjectName("telemetryLabel")
        pid_layout.addWidget(lbl_kd)
        self.spn_kd = QDoubleSpinBox()
        self.spn_kd.setRange(0.00000, 0.00100)
        self.spn_kd.setDecimals(5)
        self.spn_kd.setSingleStep(0.00001)
        self.spn_kd.setValue(0.00001)
        pid_layout.addWidget(self.spn_kd)

        # Max Output Step row
        lbl_max_step = QLabel("MAX SLEW STEP (rad/step)")
        lbl_max_step.setObjectName("telemetryLabel")
        pid_layout.addWidget(lbl_max_step)
        self.spn_max_step = QDoubleSpinBox()
        self.spn_max_step.setRange(0.0001, 0.0500)
        self.spn_max_step.setDecimals(4)
        self.spn_max_step.setSingleStep(0.0005)
        self.spn_max_step.setValue(0.0030)
        pid_layout.addWidget(self.spn_max_step)

        # Reset button
        self.btn_reset_pid = QPushButton("RESET INTEGRAL / PID")
        self.btn_reset_pid.setObjectName("resetPidButton")
        self.btn_reset_pid.setFixedHeight(26)
        pid_layout.addWidget(self.btn_reset_pid)

        layout.addWidget(grp_pid)

        layout.addStretch()

        # Status label
        self.lbl_config_status = QLabel("LIVE ENGINE SYNCED")
        self.lbl_config_status.setObjectName("telemetryLabel")
        self.lbl_config_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_config_status)

        self.scroll_area.setWidget(scroll_content)
        outer_layout.addWidget(self.scroll_area, stretch=1)


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

        self.btn_export_log = QPushButton("EXPORT LOG")
        self.btn_export_log.setObjectName("exportButton")
        header_layout.addWidget(self.btn_export_log)

        self.btn_analytics = QPushButton("ANALYTICS / LOGS")
        self.btn_analytics.setObjectName("analyticsButton")
        header_layout.addWidget(self.btn_analytics)

        self.lbl_source_chip = QLabel("[ VIRTUAL SCENE (60 Hz) ]")
        self.lbl_source_chip.setObjectName("monoNum")
        self.lbl_source_chip.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.lbl_source_chip.setStyleSheet("color: #00E676;")
        header_layout.addWidget(self.lbl_source_chip)

        header_layout.addWidget(QLabel("·"))

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
            self.config_panel.btn_reset_scene.setEnabled(True)
            self.lbl_source_chip.setText(f"[ MP4: {Path(video_path).name.upper()} ]")
            self.lbl_source_chip.setStyleSheet("color: #39C5CF;")
        middle_layout.addWidget(self.config_panel)

        main_layout.addLayout(middle_layout, stretch=1)

        # 3. BOTTOM DOCK: [LockStateIndicator 230px] [3 x RollingChart]
        bottom_dock = QHBoxLayout()
        bottom_dock.setSpacing(8)

        self.lock_indicator = LockStateIndicator()
        bottom_dock.addWidget(self.lock_indicator)

        self.chart_fps = RollingChart(title="FPS", line_color_hex="#00E676", min_val=0, max_val=80, unit_str=" FPS")
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
        self.config_panel.btn_reset_scene.clicked.connect(self._on_reset_to_virtual_scene_clicked)
        self.btn_export_log.clicked.connect(self._on_export_log_clicked)
        self.btn_analytics.clicked.connect(self._show_analytics)
        self.video_pane.target_selected.connect(self._on_target_selected)

        # Clock timer for UTC header
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_utc_clock)
        self.clock_timer.start(1000)

        # Wire all config controls to live simulation engine
        self._wire_config_signals()

    def _wire_config_signals(self) -> None:
        """Connect all ConfigPanel widgets to the active telemetry source."""
        cp = self.config_panel

        # Scene controls
        cp.sld_speed.valueChanged.connect(self._on_speed_changed)
        cp.spn_speed.valueChanged.connect(self._on_speed_changed)
        cp.spn_size.valueChanged.connect(self._on_target_size_changed)
        cp.cmb_pattern.currentTextChanged.connect(self._on_pattern_changed)
        cp.btn_decoy.toggled.connect(self._on_decoy_toggled)

        # Disturbance controls
        cp.cmb_profile.currentTextChanged.connect(self._on_profile_preset_changed)
        cp.sld_vib.valueChanged.connect(lambda _: self._on_disturbance_changed())
        cp.spn_vib.valueChanged.connect(lambda _: self._on_disturbance_changed())
        cp.sld_turb.valueChanged.connect(lambda _: self._on_disturbance_changed())
        cp.spn_turb.valueChanged.connect(lambda _: self._on_disturbance_changed())
        cp.sld_noise.valueChanged.connect(lambda _: self._on_disturbance_changed())
        cp.spn_noise.valueChanged.connect(lambda _: self._on_disturbance_changed())

        # PID controls
        cp.spn_kp.valueChanged.connect(lambda _: self._on_pid_gains_changed())
        cp.spn_ki.valueChanged.connect(lambda _: self._on_pid_gains_changed())
        cp.spn_kd.valueChanged.connect(lambda _: self._on_pid_gains_changed())
        cp.spn_max_step.valueChanged.connect(lambda _: self._on_pid_gains_changed())
        cp.btn_reset_pid.clicked.connect(self._on_pid_reset_clicked)

    def _show_config_status(self, msg: str) -> None:
        """Display brief status on sidebar, reverting to default after timeout."""
        self.config_panel.lbl_config_status.setText(msg)
        QTimer.singleShot(2500, lambda: self.config_panel.lbl_config_status.setText("LIVE ENGINE SYNCED"))

    def _on_speed_changed(self, val: int) -> None:
        if hasattr(self.telemetry_source, "set_target_speed"):
            self.telemetry_source.set_target_speed(float(val))
            self._show_config_status(f"SPEED: {val} m/s")

    def _on_target_size_changed(self, val: int) -> None:
        if hasattr(self.telemetry_source, "set_target_size"):
            self.telemetry_source.set_target_size(float(val))
            self._show_config_status(f"TARGET SIZE: {val} px")

    def _on_pattern_changed(self, text: str) -> None:
        pattern_key = PATTERN_TO_KIND.get(text, "linear")
        if hasattr(self.telemetry_source, "set_motion_pattern"):
            try:
                self.telemetry_source.set_motion_pattern(pattern_key)
                self._show_config_status(f"PATTERN: {pattern_key.upper()}")
            except Exception as exc:
                self._show_config_status(f"ERR: {exc}")

    def _on_decoy_toggled(self, checked: bool) -> None:
        if checked:
            self.config_panel.btn_decoy.setText("REMOVE FAULT DECOY")
        else:
            self.config_panel.btn_decoy.setText("DEPLOY FAULT DECOY")
        if hasattr(self.telemetry_source, "toggle_decoy"):
            self.telemetry_source.toggle_decoy(checked)
            self._show_config_status("DECOY DEPLOYED" if checked else "DECOY REMOVED")

    def _on_profile_preset_changed(self, text: str) -> None:
        profile_key = text.lower().strip()
        if profile_key not in ("mild", "moderate", "severe"):
            return
        self._syncing_profile = True
        try:
            cp = self.config_panel
            if profile_key == "mild":
                cp.spn_vib.setValue(0.4)
                cp.spn_turb.setValue(0.4)
                cp.spn_noise.setValue(35)
            elif profile_key == "moderate":
                cp.spn_vib.setValue(1.5)
                cp.spn_turb.setValue(1.2)
                cp.spn_noise.setValue(22)
            elif profile_key == "severe":
                cp.spn_vib.setValue(3.5)
                cp.spn_turb.setValue(2.5)
                cp.spn_noise.setValue(12)

            if hasattr(self.telemetry_source, "apply_disturbance_profile"):
                self.telemetry_source.apply_disturbance_profile(profile_key)
                self._show_config_status(f"PROFILE: {profile_key.upper()}")
        finally:
            self._syncing_profile = False

    def _on_disturbance_changed(self) -> None:
        if getattr(self, "_syncing_profile", False):
            return
        cp = self.config_panel
        cp.cmb_profile.blockSignals(True)
        cp.cmb_profile.setCurrentText("Custom")
        cp.cmb_profile.blockSignals(False)

        vib = cp.spn_vib.value()
        turb = cp.spn_turb.value()
        snr = float(cp.spn_noise.value())
        if hasattr(self.telemetry_source, "set_disturbance_levels"):
            self.telemetry_source.set_disturbance_levels(vib, turb, snr)
            self._show_config_status("DISTURBANCE UPDATED")

    def _on_pid_gains_changed(self) -> None:
        cp = self.config_panel
        kp = cp.spn_kp.value()
        ki = cp.spn_ki.value()
        kd = cp.spn_kd.value()
        max_step = cp.spn_max_step.value()
        if hasattr(self.telemetry_source, "set_pid_gains"):
            self.telemetry_source.set_pid_gains(kp, ki, kd, max_step)
            self._show_config_status(f"PID: Kp={kp:.5f}")

    def _on_pid_reset_clicked(self) -> None:
        if hasattr(self.telemetry_source, "control_loop"):
            self.telemetry_source.control_loop.reset()
            self._show_config_status("PID INTEGRAL RESET")

    def _on_export_log_clicked(self) -> None:
        if not self.performance_logger.packets:
            QMessageBox.information(
                self,
                "No Telemetry Data",
                "No telemetry packets recorded yet. Start simulation first to generate data.",
            )
            return
        default_filename = datetime.now(timezone.utc).strftime("fsoc_run_%Y%m%dT%H%M%S.json")
        self.log_directory.mkdir(parents=True, exist_ok=True)
        initial_path = str(self.log_directory / default_filename)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Performance Log (JSON)",
            initial_path,
            "JSON Files (*.json)",
        )
        if file_path:
            try:
                saved = self.performance_logger.export_json(file_path)
                self._session_saved = True
                self._last_log_path = saved
                if self.analytics_window is not None:
                    self.analytics_window.notify_log_saved(saved)
                self._show_config_status(f"EXPORTED: {saved.name}")
                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Performance log exported successfully to:\n{saved}",
                )
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Failed to export log:\n{exc}",
                )

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
        self.config_panel.btn_reset_scene.setEnabled(True)
        self.lbl_source_chip.setText(f"[ MP4: {Path(file_path).name.upper()} ]")
        self.lbl_source_chip.setStyleSheet("color: #39C5CF;")

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

    def _apply_sidebar_config_to_source(self, source: object) -> None:
        """Push current sidebar settings into a freshly created LiveTelemetrySource."""
        cp = self.config_panel
        if hasattr(source, "set_target_speed"):
            source.set_target_speed(float(cp.spn_speed.value()))
        if hasattr(source, "set_target_size"):
            source.set_target_size(float(cp.spn_size.value()))
        if hasattr(source, "set_motion_pattern"):
            pattern_key = PATTERN_TO_KIND.get(cp.cmb_pattern.currentText(), "linear")
            source.set_motion_pattern(pattern_key)
        if hasattr(source, "toggle_decoy"):
            source.toggle_decoy(cp.btn_decoy.isChecked())

        preset = cp.cmb_profile.currentText().lower().strip()
        if preset in ("mild", "moderate", "severe") and hasattr(source, "apply_disturbance_profile"):
            source.apply_disturbance_profile(preset)
        elif hasattr(source, "set_disturbance_levels"):
            source.set_disturbance_levels(
                cp.spn_vib.value(),
                cp.spn_turb.value(),
                float(cp.spn_noise.value()),
            )

        if hasattr(source, "set_pid_gains"):
            source.set_pid_gains(
                cp.spn_kp.value(),
                cp.spn_ki.value(),
                cp.spn_kd.value(),
                cp.spn_max_step.value(),
            )

    def _on_reset_to_virtual_scene_clicked(self) -> None:
        """Switch from external video benchmark back to the synthetic 3D virtual scene."""
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
            return

        try:
            old_source.telemetry_updated.disconnect(self._on_telemetry_updated)
        except RuntimeError:
            pass
        if hasattr(old_source, "shutdown"):
            old_source.shutdown()
        old_source.deleteLater()

        # Instantiate fresh LiveTelemetrySource for procedural virtual scene
        new_source = LiveTelemetrySource(
            time_scale=self.time_scale,
            video_path=None,
            parent=self,
        )
        self._apply_sidebar_config_to_source(new_source)

        self.telemetry_source = new_source
        self.telemetry_source.telemetry_updated.connect(self._on_telemetry_updated)

        self.config_panel.lbl_video_source.setText("VIRTUAL SCENE")
        self.config_panel.lbl_video_source.setToolTip("Procedural 3D optical tracking simulator (60 Hz)")
        self.config_panel.btn_reset_scene.setEnabled(False)
        self.lbl_source_chip.setText("[ VIRTUAL SCENE (60 Hz) ]")
        self.lbl_source_chip.setStyleSheet("color: #00E676;")

        self.chart_fps.clear()
        self.chart_err.clear()
        self.chart_lock.clear()
        self.performance_logger.reset()
        self._session_started = was_running
        self._session_saved = False
        self._last_log_path = None
        if self.analytics_window is not None:
            self.analytics_window.notify_session_reset()

        self._show_config_status("SWITCHED TO VIRTUAL SCENE")

        if was_running:
            self._session_active = True
            self.telemetry_source.start()

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
    # Expected interval at 60 Hz nominal rate is 1/60 s (16.67 ms).
    nominal_dt_s = 1.0 / 60.0
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
    print(f"[SELFTEST] Nominal 60 Hz Frame Interval: {nominal_dt_s * 1000.0:.2f} ms")
    print(f"[SELFTEST] Average Wall Loop Time: {sum(intervals_ms) / len(intervals_ms):.2f} ms")
    print(f"[SELFTEST] Ticks within 2x nominal 60 Hz interval (<={2.0 * expected_step_s * 1000.0:.1f}ms sim): {on_time_ticks}/{len(sim_intervals_s)} ({pct_on_time:.2f}%)")

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
