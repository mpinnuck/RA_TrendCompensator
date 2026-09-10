"""Shared physical constants used across the model layer."""

SIDEREAL_ARCSEC_PER_SEC = 15.041

# Hour angle advances at the sidereal rate too -- same underlying constant,
# just re-expressed as degrees per second (numerically equal to
# SIDEREAL_ARCSEC_PER_SEC only because there are 3600 of each unit per
# degree/hour respectively; not a coincidence worth relying on without the
# explicit conversion).
HOUR_ANGLE_DEG_PER_SEC = SIDEREAL_ARCSEC_PER_SEC / 3600.0


def format_pier_side(value):
	"""Convert ASCOM's PierSide enum to a readable label."""
	return {0: "East", 1: "West"}.get(value, "Unknown")


def is_known_pier_side(value):
	"""True for ASCOM's East (0) / West (1) pier sides. Some drivers
	intermittently report pierUnknown (-1) on an otherwise-unflipped mount --
	treating that as a real transition would spuriously reset the trend
	window and try to zero RightAscensionRate while the driver is in a
	state that rejects the write."""
	return value in (0, 1)
