"""Config loading/saving -- JSON-backed, matches the load_config()/save_config() pattern."""

import json
import os
import sys


def _user_data_dir():
    """OS user-data directory -- the one predictable, writable home for
    this app's own files, used as the default location for both
    config.json and (when log_folder isn't set) log files. Deliberately
    not the current working directory or the app's own install location:
    a launching process (e.g. a NINA plugin calling Process.Start()) may
    set the former to something unrelated, and the latter may not even be
    writable (e.g. an app installed under Program Files)."""
    for env_var in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOME"):
        value = os.environ.get(env_var)
        if value:
            return value
    return os.path.expanduser("~")


def _app_user_data_dir():
    path = os.path.join(_user_data_dir(), "RA_TrendCompensator")
    os.makedirs(path, exist_ok=True)
    return path


def _candidate_config_paths():
    """Legacy config file locations, checked only as migration fallbacks
    when no config.json exists yet in the current user-data location --
    lets anyone upgrading from before that location was introduced keep
    their existing settings on first launch."""
    candidates = []

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "config.json"))
    else:
        module_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(module_dir)
        candidates.append(os.path.join(project_root, "config.json"))
        if module_dir:
            candidates.append(os.path.join(module_dir, "config.json"))

    candidates.append(os.path.join(os.getcwd(), "config.json"))
    seen = set()
    ordered = []
    for path in candidates:
        norm = os.path.normcase(os.path.normpath(path))
        if norm not in seen:
            ordered.append(path)
            seen.add(norm)
    return ordered


def resolve_default_config_path(path=None):
    """Default to the OS user-data area so NINA/launcher-hosted processes
    do not silently lose settings by reading a different working directory.
    Legacy project-local config files are loaded only as migration fallbacks
    (see _candidate_config_paths)."""
    if path is not None:
        return path
    return os.path.join(_app_user_data_dir(), "config.json")


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


def load_config(path=None):
    """Load config from JSON, filling in any missing keys with defaults.
    If no path is supplied, prefer the user-data config file and only fall
    back to older project-local config files for migration compatibility."""
    config = dict(DEFAULTS)
    if path is not None:
        resolved_path = path
    else:
        default_path = resolve_default_config_path()
        if os.path.exists(default_path):
            resolved_path = default_path
        else:
            resolved_path = default_path
            for legacy_path in _candidate_config_paths():
                if os.path.exists(legacy_path):
                    resolved_path = legacy_path
                    break
    if os.path.exists(resolved_path):
        with open(resolved_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        config.update(loaded)
    return config


def save_config(config, path=None):
    """Persist config to JSON in the user-data config location by default."""
    resolved_path = resolve_default_config_path(path)
    directory = os.path.dirname(resolved_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(resolved_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def _can_write_to_directory(directory):
    """Windows ACLs are not a perfect match for os.access(), so validate with
    a real file creation attempt rather than trusting the pre-check alone."""
    try:
        if not os.access(directory, os.W_OK):
            return False
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        test_file = os.path.join(directory, ".write_test__tmp")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)
        return True
    except OSError:
        return False


def resolve_log_path(config, key):
    """Resolve a log path config key ("log_file", "data_log_file") against
    "log_folder".

    A blank log_folder resolves to the SAME OS user-data location
    config.json uses -- a fixed, predictable, always-writable place -- not
    the current working directory, which a launching process (e.g. NINA)
    may set to somewhere unrelated to where the user expects logs to land.

    When a folder IS set, only the file's basename is kept (the folder
    takes over the location) and the folder is created if needed; if that
    configured folder turns out not to be writable, this falls back to the
    same user-data location.

    An absolute path in the config value itself is always honored as-is,
    regardless of log_folder.
    """
    path = config.get(key, "")
    if path and os.path.isabs(path):
        return path

    folder = (config.get("log_folder") or "").strip()

    if folder:
        try:
            os.makedirs(folder, exist_ok=True)
            if _can_write_to_directory(folder):
                return os.path.join(folder, os.path.basename(path))
        except OSError:
            pass

    return os.path.join(_app_user_data_dir(), os.path.basename(path))
