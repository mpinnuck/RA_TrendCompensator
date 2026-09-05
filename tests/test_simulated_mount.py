"""Unit tests for SimulatedMountController -- should behave identically to
MountController's clipping/dry-run/force semantics, just without ASCOM."""

from src.model.simulated_mount import SimulatedMountController


def test_connect_sets_connected_flag():
    mount = SimulatedMountController(max_rate_magnitude=1.0, logger=lambda msg: None)
    assert mount.connected is False
    mount.connect()
    assert mount.connected is True


def test_set_ra_rate_clips_to_max_magnitude():
    mount = SimulatedMountController(max_rate_magnitude=0.5, logger=lambda msg: None)
    mount.set_ra_rate(2.0, dry_run=False)
    assert mount.get_ra_rate() == 0.5
    mount.set_ra_rate(-2.0, dry_run=False)
    assert mount.get_ra_rate() == -0.5


def test_dry_run_does_not_change_rate_unless_forced():
    mount = SimulatedMountController(max_rate_magnitude=1.0, logger=lambda msg: None)
    mount.set_ra_rate(0.3, dry_run=True)
    assert mount.get_ra_rate() == 0.0

    mount.set_ra_rate(0.3, dry_run=True, force=True)
    assert mount.get_ra_rate() == 0.3


def test_disconnect_resets_rate_to_zero_even_in_dry_run():
    mount = SimulatedMountController(max_rate_magnitude=1.0, logger=lambda msg: None)
    mount.set_ra_rate(0.3, dry_run=False)
    assert mount.get_ra_rate() == 0.3

    mount.disconnect()
    assert mount.get_ra_rate() == 0.0
    assert mount.connected is False


def test_declination_defaults_to_zero():
    mount = SimulatedMountController(max_rate_magnitude=1.0, logger=lambda msg: None)
    assert mount.get_declination() == 0.0


def test_declination_can_be_set_at_construction():
    mount = SimulatedMountController(max_rate_magnitude=1.0, logger=lambda msg: None, declination_deg=-63.8)
    assert mount.get_declination() == -63.8


def test_declination_can_be_changed_after_construction():
    mount = SimulatedMountController(max_rate_magnitude=1.0, logger=lambda msg: None)
    mount.set_declination(-45.0)
    assert mount.get_declination() == -45.0
