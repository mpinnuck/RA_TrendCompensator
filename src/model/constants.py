"""Shared physical constants used across the model layer."""

SIDEREAL_ARCSEC_PER_SEC = 15.041

# Hour angle advances at the sidereal rate too -- same underlying constant,
# just re-expressed as degrees per second (numerically equal to
# SIDEREAL_ARCSEC_PER_SEC only because there are 3600 of each unit per
# degree/hour respectively; not a coincidence worth relying on without the
# explicit conversion).
HOUR_ANGLE_DEG_PER_SEC = SIDEREAL_ARCSEC_PER_SEC / 3600.0
