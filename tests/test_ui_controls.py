"""tests/test_ui_controls.py -- Verification of cockpit UI controls and their live engine wiring."""

from __future__ import annotations

import os
import pytest
from PySide6.QtWidgets import QApplication

from core.contracts import TrackState
from ui.main_window import MainWindow, PATTERN_TO_KIND, MOTION_PATTERN_OPTIONS


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_config_panel_widgets_presence(qapp):
    """Verify that all mission-control widgets and groups are instantiated."""
    win = MainWindow(use_live_source=True)
    cp = win.config_panel

    # Scroll container
    assert cp.scroll_area is not None
    assert cp.scroll_area.widget() is not None

    # Core actions
    assert cp.btn_run is not None
    assert win.btn_export_log is not None
    assert win.btn_analytics is not None

    # Scene controls
    assert cp.sld_speed is not None
    assert cp.spn_speed is not None
    assert cp.spn_size is not None
    assert cp.cmb_pattern is not None
    assert cp.cmb_pattern.count() == len(MOTION_PATTERN_OPTIONS)

    # Fault injection
    assert cp.btn_decoy is not None
    assert cp.btn_decoy.isCheckable()

    # Disturbance models
    assert cp.cmb_profile is not None
    assert cp.sld_vib is not None
    assert cp.spn_vib is not None
    assert cp.sld_turb is not None
    assert cp.spn_turb is not None
    assert cp.sld_noise is not None
    assert cp.spn_noise is not None

    # PID controller
    assert cp.spn_kp is not None
    assert cp.spn_ki is not None
    assert cp.spn_kd is not None
    assert cp.spn_max_step is not None
    assert cp.btn_reset_pid is not None

    # Status indicator
    assert cp.lbl_config_status is not None

    win.close()


def test_target_speed_wiring(qapp):
    """Verify target speed slider updates live telemetry source."""
    win = MainWindow(use_live_source=True)
    cp = win.config_panel
    source = win.telemetry_source

    cp.sld_speed.setValue(45)
    assert cp.spn_speed.value() == 45
    assert source._target_speed_m_s == 45.0

    cp.spn_speed.setValue(30)
    assert cp.sld_speed.value() == 30
    assert source._target_speed_m_s == 30.0

    win.close()


def test_target_size_wiring(qapp):
    """Verify target size spinbox updates live telemetry source."""
    win = MainWindow(use_live_source=True)
    cp = win.config_panel
    source = win.telemetry_source

    cp.spn_size.setValue(12)
    assert source._target_size_px == 12.0

    win.close()


def test_motion_pattern_wiring(qapp):
    """Verify motion pattern selector updates live telemetry source scene."""
    win = MainWindow(use_live_source=True)
    cp = win.config_panel
    source = win.telemetry_source

    for pattern_label in MOTION_PATTERN_OPTIONS:
        cp.cmb_pattern.setCurrentText(pattern_label)
        expected_kind = PATTERN_TO_KIND[pattern_label]
        assert source._motion_pattern == expected_kind
        assert source.scene is not None
        assert source.scene.beacon_configs[0].motion == (
            "sinusoidal" if expected_kind in ("sinusoidal", "lissajous") else expected_kind
        )

    win.close()


def test_decoy_toggle_wiring(qapp):
    """Verify fault decoy button toggles distractor beacon in live scene."""
    win = MainWindow(use_live_source=True)
    cp = win.config_panel
    source = win.telemetry_source

    assert not source._decoy_enabled
    assert len(source.scene.beacon_configs) == 1

    # Deploy decoy
    cp.btn_decoy.setChecked(True)
    assert cp.btn_decoy.text() == "REMOVE FAULT DECOY"
    assert source._decoy_enabled is True
    assert len(source.scene.beacon_configs) == 2
    assert source.scene.beacon_configs[1].role == "distractor"

    # Remove decoy
    cp.btn_decoy.setChecked(False)
    assert cp.btn_decoy.text() == "DEPLOY FAULT DECOY"
    assert source._decoy_enabled is False
    assert len(source.scene.beacon_configs) == 1

    win.close()


def test_disturbance_presets_and_sliders_wiring(qapp):
    """Verify disturbance presets and custom sliders update live pipeline."""
    win = MainWindow(use_live_source=True)
    cp = win.config_panel
    source = win.telemetry_source

    # Apply moderate preset
    cp.cmb_profile.setCurrentText("Moderate")
    assert pytest.approx(source._vib_sigma, 0.01) == 1.5
    assert pytest.approx(source._turb_sigma, 0.01) == 1.2
    assert pytest.approx(source._noise_snr_db, 0.01) == 22.0

    # Adjust individual slider -> switches profile to 'Custom'
    cp.sld_vib.setValue(25)  # 2.5 px
    assert cp.cmb_profile.currentText() == "Custom"
    assert pytest.approx(source._vib_sigma, 0.01) == 2.5

    win.close()


def test_pid_tuning_and_reset_wiring(qapp):
    """Verify PID spinboxes and reset button update live controller."""
    win = MainWindow(use_live_source=True)
    cp = win.config_panel
    source = win.telemetry_source

    cp.spn_kp.setValue(0.00065)
    cp.spn_ki.setValue(0.00003)
    cp.spn_kd.setValue(0.00004)
    cp.spn_max_step.setValue(0.0045)

    pid = source.control_loop.pid
    assert pid.pan_pid.kp == 0.00065
    assert pid.pan_pid.ki == 0.00003
    assert pid.pan_pid.kd == 0.00004
    assert pid.pan_pid.max_output_step == 0.0045

    assert pid.tilt_pid.kp == 0.00065
    assert pid.tilt_pid.ki == 0.00003
    assert pid.tilt_pid.kd == 0.00004
    assert pid.tilt_pid.max_output_step == 0.0045

    # Simulate some integral accumulation
    pid.pan_pid._integral = 42.0
    cp.btn_reset_pid.click()
    assert pid.pan_pid._integral == 0.0

    win.close()


def test_switch_back_to_virtual_scene_wiring(qapp, tmp_path):
    """Verify switching back from video benchmark to synthetic virtual scene."""
    win = MainWindow(use_live_source=True)
    cp = win.config_panel
    assert cp.btn_reset_scene is not None
    assert not cp.btn_reset_scene.isEnabled()
    assert "VIRTUAL SCENE" in cp.lbl_video_source.text()
    assert "VIRTUAL SCENE" in win.lbl_source_chip.text()

    # Simulate being in loaded video state
    win.config_panel.lbl_video_source.setText("TEST_BENCHMARK.MP4")
    win.config_panel.btn_reset_scene.setEnabled(True)
    win.lbl_source_chip.setText("[ MP4: TEST_BENCHMARK.MP4 ]")

    # Set custom parameters in sidebar before switching
    cp.spn_speed.setValue(40)
    cp.spn_size.setValue(10)
    cp.cmb_pattern.setCurrentText("Archimedean Spiral")
    cp.btn_decoy.setChecked(True)

    # Click switch to virtual scene
    cp.btn_reset_scene.click()

    # Verify source was replaced with a virtual scene LiveTelemetrySource
    assert not cp.btn_reset_scene.isEnabled()
    assert "VIRTUAL SCENE" in cp.lbl_video_source.text()
    assert "VIRTUAL SCENE" in win.lbl_source_chip.text()
    assert win.telemetry_source.video_adapter is None
    assert win.telemetry_source.scene is not None

    # Verify sidebar settings were carried over to the new virtual scene
    assert win.telemetry_source._target_speed_m_s == 40.0
    assert win.telemetry_source._target_size_px == 10.0
    assert win.telemetry_source._motion_pattern == "spiral"
    assert win.telemetry_source._decoy_enabled is True
    assert len(win.telemetry_source.scene.beacon_configs) == 2

    # Verify 60 FPS nominal step
    packet, img = win.telemetry_source.step()
    assert packet.fps == 60.0

    win.close()

