"""Offscreen tests for live analytics, archived logs, and run finalization."""

from __future__ import annotations

import json
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QApplication

from core.contracts import TelemetryPacket, TrackState
from telemetry.performance_logger import PerformanceLogger
from ui.analytics_window import (
    AnalyticsWindow,
    SessionTrendChart,
    TelemetryTableModel,
    load_performance_log,
)
from ui.main_window import MainWindow


def get_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_packet(
    frame_id: int,
    state: TrackState = TrackState.TRACK,
    error_px: tuple[float, float] = (3.0, 4.0),
) -> TelemetryPacket:
    return TelemetryPacket(
        frame_id=frame_id,
        timestamp_s=frame_id / 30.0,
        fps=30.0 + frame_id / 10.0,
        track_state=state,
        error_px=error_px,
        error_az_rad=0.001 * frame_id,
        error_el_rad=-0.001 * frame_id,
        lock_fraction=0.8,
        acquisition_time_s=0.4 if state is TrackState.TRACK else float("nan"),
        loop_time_s=0.005,
    )


def test_telemetry_table_model_formats_and_sorts_typed_values():
    get_qapp()
    packets = [
        make_packet(10),
        make_packet(2, TrackState.SEARCH, (float("nan"), float("nan"))),
        make_packet(3, TrackState.ACQUIRE),
        make_packet(4, TrackState.REACQUIRE),
    ]
    model = TelemetryTableModel(packets)

    assert model.columnCount() == 12
    assert model.rowCount() == 4
    assert model.data(model.index(1, 5)) == "N/A"
    assert model.data(model.index(0, 4)) == "5.000"
    assert model.headerData(8, Qt.Orientation.Horizontal) == "AZ ERR (mrad)"

    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setSortRole(Qt.ItemDataRole.UserRole)
    proxy.sort(0, Qt.SortOrder.AscendingOrder)
    assert proxy.data(proxy.index(0, 0), Qt.ItemDataRole.UserRole) == 2

    proxy.setFilterKeyColumn(2)
    proxy.setFilterFixedString("TRACK")
    assert proxy.rowCount() == 1


def test_exact_state_filter_does_not_mix_acquire_and_reacquire(tmp_path):
    get_qapp()
    logger = PerformanceLogger()
    logger.record(make_packet(1, TrackState.ACQUIRE))
    logger.record(make_packet(2, TrackState.REACQUIRE))
    window = AnalyticsWindow(logger, tmp_path)
    try:
        window.state_filter.setCurrentText("ACQUIRE")
        assert window.proxy_model.rowCount() == 1
        assert window.proxy_model.data(window.proxy_model.index(0, 2)) == "ACQUIRE"
    finally:
        window.close()


def test_full_session_chart_downsampling_keeps_spikes_and_gaps():
    get_qapp()
    chart = SessionTrendChart("Test", "#39C5CF", "px", 10.0)
    series = [(float(index), 1.0) for index in range(200)]
    series[99] = (99.0, 500.0)
    series[100] = (100.0, float("nan"))
    chart.set_series(series)

    rendered = chart._render_series(25)
    assert (99.0, 500.0) in rendered
    assert any(not math.isfinite(value) for _, value in rendered)


def test_analytics_window_summarizes_filters_and_exports(tmp_path):
    app = get_qapp()
    logger = PerformanceLogger()
    logger.record(make_packet(0, TrackState.SEARCH, (float("nan"), float("nan"))))
    for frame_id in range(1, 202):
        logger.record(make_packet(frame_id))

    window = AnalyticsWindow(logger, tmp_path)
    try:
        window.show()
        app.processEvents()
        window.refresh_data(force=True)

        assert window.metric_cards["total_frames"].value_label.text() == "202"
        assert window.metric_cards["mean_error_px"].value_label.text() == "5.00 px"
        assert window.table_model.rowCount() == 202
        assert len(window.chart_fps._series) == 202

        window.state_filter.setCurrentText("SEARCH")
        assert window.proxy_model.rowCount() == 1
        assert window.row_count_label.text() == "1 / 202 ROWS"

        json_path = window.export_json_to(tmp_path / "manual_export.json")
        csv_path = window.export_csv_to(tmp_path / "manual_export.csv")
        assert json_path.is_file()
        assert csv_path.is_file()
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert len(payload["packets"]) == 202
        assert payload["packets"][1]["loop_time_s"] == 0.005
    finally:
        window.close()


def test_load_performance_log_accepts_legacy_missing_fields(tmp_path):
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(
        json.dumps(
            {
                "summary": {},
                "packets": [
                    {
                        "frame_id": 9,
                        "timestamp_s": 0.3,
                        "fps": 30.0,
                        "track_state": "LOST",
                        "error_px": [None, None],
                        "lock_fraction": 0.25,
                        "acquisition_time_s": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    logger = load_performance_log(legacy_path)
    packet = logger.packets[0]
    assert packet.frame_id == 9
    assert packet.track_state is TrackState.LOST
    assert math.isnan(packet.error_az_rad)
    assert math.isnan(packet.error_el_rad)
    assert math.isnan(packet.loop_time_s)


def test_main_window_opens_one_analytics_page_and_auto_saves_run(tmp_path):
    app = get_qapp()
    window = MainWindow(log_directory=tmp_path)
    try:
        window.show()
        window.config_panel.btn_run.click()
        window.telemetry_source.stop()

        for _ in range(5):
            packet, image = window.telemetry_source.step()
            window._on_telemetry_updated(packet, image)

        window.btn_analytics.click()
        app.processEvents()
        analytics = window.analytics_window
        assert analytics is not None
        assert analytics.isWindow()
        assert analytics.isVisible()
        analytics.refresh_data(force=True)
        assert analytics.table_model.rowCount() == 5

        window.btn_analytics.click()
        app.processEvents()
        assert window.analytics_window is analytics

        window.config_panel.btn_run.click()
        app.processEvents()
        saved_logs = list(tmp_path.glob("fsoc_run_*.json"))
        assert len(saved_logs) == 1
        payload = json.loads(saved_logs[0].read_text(encoding="utf-8"))
        assert len(payload["packets"]) == 5
        assert set(payload["packets"][0]) == {
            "frame_id",
            "timestamp_s",
            "fps",
            "track_state",
            "error_px",
            "error_az_rad",
            "error_el_rad",
            "lock_fraction",
            "acquisition_time_s",
            "loop_time_s",
        }
        analytics.refresh_saved_runs()
        assert analytics.dataset_combo.findData(str(saved_logs[0].resolve())) >= 0

        window.config_panel.btn_run.click()
        window.telemetry_source.stop()
        for _ in range(2):
            packet, image = window.telemetry_source.step()
            window._on_telemetry_updated(packet, image)
        window.config_panel.btn_run.click()
        updated_logs = list(tmp_path.glob("fsoc_run_*.json"))
        assert updated_logs == saved_logs
        updated_payload = json.loads(saved_logs[0].read_text(encoding="utf-8"))
        assert len(updated_payload["packets"]) == 7
    finally:
        window.close()
        app.processEvents()

    assert len(list(tmp_path.glob("fsoc_run_*.json"))) == 1


def test_refreshing_deleted_external_log_returns_to_live_dataset(tmp_path):
    get_qapp()
    live_logger = PerformanceLogger()
    live_logger.record(make_packet(1))
    archived_logger = PerformanceLogger()
    archived_logger.record(make_packet(99, TrackState.LOST))
    external_path = tmp_path / "external.json"
    archived_logger.export_json(external_path)

    window = AnalyticsWindow(live_logger, tmp_path / "automatic_logs")
    try:
        window.dataset_combo.addItem("EXTERNAL", str(external_path.resolve()))
        window.dataset_combo.setCurrentIndex(window.dataset_combo.count() - 1)
        assert window.displayed_logger.packets[0].frame_id == 99

        external_path.unlink()
        window.refresh_saved_runs()
        assert window.dataset_combo.currentData() is None
        assert window.displayed_logger is live_logger
        assert window.table_model.data(window.table_model.index(0, 0)) == "000001"
    finally:
        window.close()
