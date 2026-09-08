"""Config loading/saving -- JSON-backed, matches the load_config()/save_config() pattern."""

import json
import os

DEFAULT_CONFIG_PATH = "config.json"

DEFAULTS = {
    "phd2_host": "localhost",
    "phd2_port": 4400,
    "ascom_prog_id": "ASCOM.ASIMount.Telescope",
    "dry_run": False,
    "window_seconds": 300,
    "min_samples_for_trend": 60,
    "apply_interval_seconds": 120,
    "damping_factor": 0.3,
    "max_rate_magnitude": 1.0,
    "max_step_per_cycle": 0.05,
    "pixel_scale_arcsec": 0.51,
    "autostart": False,
    "maintain_interval_seconds": 60,
    "log_folder": "",
    "log_file": "ra_trend_compensator.log",
    "data_log_file": "ra_trend_compensator_data.csv",
    "chart_history_hours": 8,
    "simulation_mode": False,
    "sim_true_drift_arcsec_per_sec": 0.02,
    "sim_drift_walk_std": 0.0008,
    "sim_drift_ramp_arcsec_per_sec_per_hour": 0.0,
    "sim_drift_profile": None,
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
    "status_server_enabled": True,
    "status_server_host": "127.0.0.1",
    "status_server_port": 4401,
    "status_server_interval_seconds": 1.0,
    "rms_window_seconds": 300,
    "rms_trend_window_seconds": 1800,
    "rms_sample_interval_seconds": 60,
}


def load_config(path=DEFAULT_CONFIG_PATH):
    """Load config from JSON, filling in any missing keys with defaults."""
    config = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        config.update(loaded)
    return config


def save_config(config, path=DEFAULT_CONFIG_PATH):
    """Persist config to JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def resolve_log_path(config, key):
    """Resolve a log path config key ("log_file", "data_log_file") against
    "log_folder". A blank log_folder means the app folder -- the configured
    path is used exactly as-is. When a folder is set, only the file's
    basename is kept (the folder takes over the location), and the folder
    is created if it doesn't exist yet."""
    path = config.get(key, "")
    folder = (config.get("log_folder") or "").strip()
    if not folder:
        return path
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, os.path.basename(path))
