"""Configuration default tests."""

from src.config import load_config


def test_dry_run_is_disabled_by_default(tmp_path):
    config = load_config(tmp_path / "missing-config.json")

    assert config["dry_run"] is False