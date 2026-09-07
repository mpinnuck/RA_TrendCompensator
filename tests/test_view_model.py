"""ViewModel tests -- driven with fake mount/PHD2 clients, no hardware needed."""

import pytest

import src.viewmodel.view_model as vm_module
from tests.fakes import FakeMountController, FakePHD2Client


@pytest.fixture
def config(tmp_path):
    return {
        "phd2_host": "localhost",
        "phd2_port": 4400,
        "ascom_prog_id": "FAKE",
        "dry_run": False,
        "window_seconds": 30,
        "min_samples_for_trend": 3,
        "apply_interval_seconds": 0,
        "damping_factor": 0.3,
        "max_rate_magnitude": 1.0,
        "max_step_per_cycle": 0.05,
        "pixel_scale_arcsec": 0.5,
        "log_file": str(tmp_path / "test.log"),
        "data_log_file": str(tmp_path / "test_data.csv"),
        "chart_history_hours": 8,
        "status_server_enabled": False,
        "rms_window_seconds": 60,
        "rms_trend_window_seconds": 300,
        "rms_sample_interval_seconds": 5,
    }


@pytest.fixture
def view_model(monkeypatch, config):
    monkeypatch.setattr(vm_module, "MountController", FakeMountController)
    monkeypatch.setattr(vm_module, "PHD2Client", FakePHD2Client)
    return vm_module.RATrendCompensatorViewModel(config)


def test_guide_steps_feed_the_drift_chart_history(view_model):
    for px in [1.0, 1.2, 1.5, 1.8, 2.1]:
        view_model._on_guide_step({"RADistanceRaw": px})

    samples, _ = view_model.get_drift_snapshot()
    assert len(samples) == 5


def test_phd2_avg_dist_is_extracted_when_present(view_model, config):
    view_model._on_guide_step({"RADistanceRaw": 2.0, "AvgDist": 1.5})

    assert view_model.last_phd2_avg_dist_arcsec == pytest.approx(1.5 * config["pixel_scale_arcsec"])


def test_phd2_avg_dist_defaults_to_none_without_the_field(view_model):
    view_model._on_guide_step({"RADistanceRaw": 2.0})  # no AvgDist key at all

    assert view_model.last_phd2_avg_dist_arcsec is None


def test_phd2_avg_dist_appears_in_status_snapshot(view_model, config):
    view_model._on_guide_step({"RADistanceRaw": 2.0, "AvgDist": 1.5})

    snapshot = view_model.get_status_snapshot()

    assert snapshot["phd2_avg_dist_arcsec"] == pytest.approx(1.5 * config["pixel_scale_arcsec"])


def test_phd2_avg_dist_is_logged_to_the_data_csv(view_model, config):
    view_model._on_guide_step({"RADistanceRaw": 2.0, "AvgDist": 1.5})

    with open(config["data_log_file"], newline="", encoding="utf-8") as f:
        import csv
        rows = [r for r in csv.DictReader(f) if r["event_type"] == "guide_step"]

    assert float(rows[0]["phd2_avg_dist_arcsec"]) == pytest.approx(1.5 * config["pixel_scale_arcsec"])


def test_sustained_drift_produces_a_nonzero_rate_offset(view_model):
    # A steadily increasing raw RA error should drive a nonzero corrective offset.
    for i in range(10):
        view_model._on_guide_step({"RADistanceRaw": i * 0.5})

    assert view_model.current_offset != 0.0
    _, rate_changes = view_model.get_drift_snapshot()
    assert len(rate_changes) >= 1


def test_pier_flip_resets_offset_and_records_a_rate_change(view_model):
    view_model.mount.side_of_pier = 0
    for i in range(10):
        view_model._on_guide_step({"RADistanceRaw": i * 0.5})
    assert view_model.current_offset != 0.0

    view_model.mount.side_of_pier = 1  # simulate a pier flip
    view_model._on_guide_step({"RADistanceRaw": 5.0})

    assert view_model.current_offset == 0.0
    _, rate_changes = view_model.get_drift_snapshot()
    assert rate_changes[-1][1] == 0.0


def test_guide_steps_are_logged_to_the_data_csv(view_model, config):
    for px in [1.0, 1.2, 1.5]:
        view_model._on_guide_step({"RADistanceRaw": px})

    with open(config["data_log_file"], newline="", encoding="utf-8") as f:
        import csv
        rows = [r for r in csv.DictReader(f) if r["event_type"] == "guide_step"]

    assert len(rows) == 3
    assert rows[0]["ra_raw_arcsec"] == str(1.0 * config["pixel_scale_arcsec"])


def test_adjustment_cycles_are_logged_with_the_rate_that_produced_them(view_model, config):
    # min_samples_for_trend=3, apply_interval_seconds=0 in the config fixture,
    # so every guide step after the 3rd should trigger an adjustment.
    for i in range(10):
        view_model._on_guide_step({"RADistanceRaw": i * 0.5})

    with open(config["data_log_file"], newline="", encoding="utf-8") as f:
        import csv
        rows = [r for r in csv.DictReader(f) if r["event_type"] == "adjustment"]

    assert len(rows) >= 1
    first_row = rows[0]
    # The very first adjustment should be measured against a rate of 0
    # (nothing applied yet) -- exactly the pairing needed for calibration.
    assert first_row["previous_ra_rate"] == "0.0"
    assert float(first_row["slope_arcsec_per_sec"]) != 0.0
    assert first_row["dry_run"] == str(view_model.dry_run)


def test_update_config_rebuilds_models_and_persists(monkeypatch, view_model, config):
    save_calls = []
    monkeypatch.setattr(vm_module, "save_config", lambda cfg: save_calls.append(cfg))

    new_config = dict(config)
    new_config["phd2_port"] = 5555
    new_config["chart_history_hours"] = 2

    view_model.update_config(new_config)

    assert view_model.config["phd2_port"] == 5555
    assert view_model.drift_history.max_seconds == 2 * 3600
    assert save_calls and save_calls[-1]["phd2_port"] == 5555


def test_update_config_refuses_while_running(view_model):
    view_model.running = True
    with pytest.raises(RuntimeError):
        view_model.update_config(dict(view_model.config))


def test_get_status_snapshot_reflects_current_state(view_model):
    for i in range(10):
        view_model._on_guide_step({"RADistanceRaw": i * 0.5})

    snapshot = view_model.get_status_snapshot()

    assert snapshot["running"] is False  # start() was never called in this fixture
    assert snapshot["phd2_connected"] is False
    assert snapshot["dry_run"] == view_model.dry_run
    assert snapshot["current_offset"] == view_model.current_offset
    assert snapshot["current_ra_deviation_arcsec"] == view_model.last_raw_arcsec
    assert snapshot["current_ra_deviation_arcsec"] is not None
    assert snapshot["last_slope_arcsec_per_sec"] is not None
    assert snapshot["last_trend_n_samples"] >= 1
    assert "timestamp" in snapshot
    assert snapshot["guide_rms_arcsec"] is not None
    assert snapshot["guide_rms_arcsec"] >= 0.0


def test_status_server_is_none_when_disabled(view_model):
    assert view_model.status_server is None  # config fixture sets status_server_enabled=False
    assert view_model.get_status_client_count() == 0


def test_shutdown_stops_a_running_session(view_model):
    view_model.mount.connect()
    view_model.running = True

    view_model.shutdown()

    assert view_model.running is False


def test_status_server_enabled_creates_and_tears_down_a_real_server(monkeypatch, config):
    from tests.fakes import FakeMountController, FakePHD2Client
    monkeypatch.setattr(vm_module, "MountController", FakeMountController)
    monkeypatch.setattr(vm_module, "PHD2Client", FakePHD2Client)

    config = dict(config)
    config["status_server_enabled"] = True
    config["status_server_host"] = "127.0.0.1"
    config["status_server_port"] = 0  # OS-assigned free port
    config["status_server_interval_seconds"] = 0.05

    vm = vm_module.RATrendCompensatorViewModel(config)
    try:
        assert vm.status_server is not None
    finally:
        vm.shutdown()
