"""Configuration default tests."""

import os

from src import config as config_module
from src.config import load_config, resolve_log_path


def test_dry_run_is_disabled_by_default(tmp_path):
    config = load_config(tmp_path / "missing-config.json")

    assert config["dry_run"] is False


def test_resolve_log_path_falls_back_to_user_data_dir_when_working_dir_is_not_writable(monkeypatch, tmp_path):
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    writable_root = tmp_path / "localappdata"
    writable_root.mkdir()

    monkeypatch.chdir(readonly_dir)
    monkeypatch.setenv("LOCALAPPDATA", str(writable_root))

    def fake_access(path, mode):
        return not os.path.normcase(os.path.normpath(str(path))) == os.path.normcase(str(readonly_dir))

    monkeypatch.setattr(config_module.os, "access", fake_access)

    config = {"log_file": "ra_trend_compensator.log", "data_log_file": "ra_trend_compensator_data.csv"}

    assert resolve_log_path(config, "log_file") == str(writable_root / "RA_TrendCompensator" / "ra_trend_compensator.log")
    assert resolve_log_path(config, "data_log_file") == str(writable_root / "RA_TrendCompensator" / "ra_trend_compensator_data.csv")


def test_resolve_log_path_falls_back_when_configured_log_folder_is_not_writable(monkeypatch, tmp_path):
    writable_root = tmp_path / "localappdata"
    writable_root.mkdir()
    protected_dir = tmp_path / "protected_logs"
    protected_dir.mkdir()

    monkeypatch.setenv("LOCALAPPDATA", str(writable_root))

    def fake_access(path, mode):
        return not os.path.normcase(os.path.normpath(str(path))) == os.path.normcase(str(protected_dir))

    monkeypatch.setattr(config_module.os, "access", fake_access)

    config = {
        "log_folder": str(protected_dir),
        "log_file": "ra_trend_compensator.log",
        "data_log_file": "ra_trend_compensator_data.csv",
    }

    assert resolve_log_path(config, "log_file") == str(writable_root / "RA_TrendCompensator" / "ra_trend_compensator.log")
    assert resolve_log_path(config, "data_log_file") == str(writable_root / "RA_TrendCompensator" / "ra_trend_compensator_data.csv")


def test_resolve_log_path_honors_explicit_absolute_paths(monkeypatch, tmp_path):
    writable_root = tmp_path / "localappdata"
    writable_root.mkdir()
    explicit_dir = tmp_path / "explicit_logs"
    explicit_dir.mkdir()

    monkeypatch.setenv("LOCALAPPDATA", str(writable_root))

    config = {
        "log_folder": str(explicit_dir),
        "log_file": str(explicit_dir / "ra_trend_compensator.log"),
        "data_log_file": str(explicit_dir / "ra_trend_compensator_data.csv"),
    }

    assert resolve_log_path(config, "log_file") == str(explicit_dir / "ra_trend_compensator.log")
    assert resolve_log_path(config, "data_log_file") == str(explicit_dir / "ra_trend_compensator_data.csv")


def test_default_config_path_prefers_user_data_area(monkeypatch, tmp_path):
    writable_root = tmp_path / "localappdata"
    writable_root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(writable_root))

    config_path = config_module.resolve_default_config_path()

    assert config_path == str(writable_root / "RA_TrendCompensator" / "config.json")
