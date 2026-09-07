"""Unit tests for MountController.get_declination() -- the rest of
MountController (connect/set_ra_rate) needs a real ASCOM driver and isn't
covered here; this only exercises the read path, which is safe to test
against a stand-in .telescope object without ever calling connect()."""

import types

from src.model.mount_controller import MountController


def test_get_declination_reads_the_ascom_property():
    mount = MountController("FAKE.ProgID", max_rate_magnitude=1.0, logger=lambda msg: None)
    mount.telescope = types.SimpleNamespace(Declination=-63.8)

    assert mount.get_declination() == -63.8


def test_get_side_of_pier_returns_the_ascom_value():
    mount = MountController("FAKE.ProgID", max_rate_magnitude=1.0, logger=lambda msg: None)

    mount.telescope = types.SimpleNamespace(SideOfPier=0)
    assert mount.get_side_of_pier() == 0

    mount.telescope = types.SimpleNamespace(SideOfPier=1)
    assert mount.get_side_of_pier() == 1


def test_get_declination_returns_none_on_driver_error():
    mount = MountController("FAKE.ProgID", max_rate_magnitude=1.0, logger=lambda msg: None)

    class BoomOnAccess:
        @property
        def Declination(self):
            raise RuntimeError("simulated COM error")

    mount.telescope = BoomOnAccess()

    assert mount.get_declination() is None
