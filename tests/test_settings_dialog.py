"""SettingsDialog tests -- run against a hidden Tk root, no visible window."""

import pytest

tk = pytest.importorskip("tkinter")

from src.view.settings_dialog import SettingsDialog

SAMPLE_CONFIG = {
    "phd2_host": "localhost",
    "phd2_port": 4400,
    "ascom_prog_id": "ASCOM.ASIMount.Telescope",
    "dry_run": True,
    "window_seconds": 300,
    "min_samples_for_trend": 60,
    "apply_interval_seconds": 120,
    "damping_factor": 0.3,
    "max_rate_magnitude": 1.0,
    "max_step_per_cycle": 0.05,
    "pixel_scale_arcsec": 0.51,
    "log_file": "ra_trend_compensator.log",
    "data_log_file": "ra_trend_compensator_data.csv",
    "chart_history_hours": 8,
    "simulation_mode": False,
    "sim_true_drift_arcsec_per_sec": 0.02,
    "sim_drift_walk_std": 0.0008,
    "sim_drift_ramp_arcsec_per_sec_per_hour": 0.0,
    "sim_noise_arcsec": 0.15,
    "sim_pull_to_zero_per_step": 0.001,
    "sim_guide_step_interval_s": 2.0,
    "sim_speed_multiplier": 1.0,
    "sim_declination_deg": 0.0,
    "sim_target_name": "",
    "sim_target_ra_hours": 0.0,
    "sim_start_hour_angle_hours": 0.0,
    "sim_polar_error_arcmin": 0.0,
    "sim_polar_error_angle_deg": 0.0,
    "sim_bias_direction": "west",
}


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk is unavailable: {error}")
    r.withdraw()  # headless -- don't flash a window during test runs
    yield r
    r.destroy()


def test_save_parses_fields_and_carries_over_untouched_ones(root):
    saved = {}

    dlg = SettingsDialog(root, dict(SAMPLE_CONFIG), lambda cfg: saved.update(cfg))
    dlg.vars["phd2_port"].set("4401")
    dlg.vars["damping_factor"].set("0.5")
    dlg._on_save_clicked()

    assert saved["phd2_port"] == 4401
    assert isinstance(saved["phd2_port"], int)
    assert saved["damping_factor"] == 0.5
    # untouched field is carried over unchanged, not dropped
    assert saved["dry_run"] is True
    assert saved["ascom_prog_id"] == SAMPLE_CONFIG["ascom_prog_id"]


def test_invalid_number_is_rejected_without_calling_on_save(root):
    called = []
    dlg = SettingsDialog(root, dict(SAMPLE_CONFIG), lambda cfg: called.append(cfg))

    dlg.vars["phd2_port"].set("not-a-number")
    dlg._on_save_clicked()

    assert called == []
    assert "PHD2 port" in dlg.error_var.get()
    dlg.destroy()


def test_cancel_does_not_call_on_save(root):
    called = []
    dlg = SettingsDialog(root, dict(SAMPLE_CONFIG), lambda cfg: called.append(cfg))
    dlg._on_cancel()
    assert called == []


def test_simulation_mode_checkbox_round_trips_as_bool(root):
    saved = {}
    dlg = SettingsDialog(root, dict(SAMPLE_CONFIG), lambda cfg: saved.update(cfg))
    dlg.vars["simulation_mode"].set(True)
    dlg._on_save_clicked()

    assert saved["simulation_mode"] is True


def test_no_profile_loaded_by_default_when_config_has_none(root):
    saved = {}
    dlg = SettingsDialog(root, dict(SAMPLE_CONFIG), lambda cfg: saved.update(cfg))
    dlg._on_save_clicked()

    assert saved["sim_drift_profile"] is None


def test_load_profile_button_sets_the_profile(root):
    from src.model.real_session_profiles import PROFILES, NGC6744_2026_09_03

    saved = {}
    dlg = SettingsDialog(root, dict(SAMPLE_CONFIG), lambda cfg: saved.update(cfg))
    dlg._load_profile("NGC6744_2026_09_03")
    dlg._on_save_clicked()

    assert saved["sim_drift_profile"] == NGC6744_2026_09_03
    assert "NGC6744_2026_09_03" in PROFILES  # sanity: the name used above is real


def test_clear_profile_button_removes_a_previously_loaded_profile(root):
    from src.model.real_session_profiles import NGC6744_2026_09_03

    config_with_profile = dict(SAMPLE_CONFIG)
    config_with_profile["sim_drift_profile"] = list(NGC6744_2026_09_03)

    saved = {}
    dlg = SettingsDialog(root, config_with_profile, lambda cfg: saved.update(cfg))
    dlg._clear_profile()
    dlg._on_save_clicked()

    assert saved["sim_drift_profile"] is None
