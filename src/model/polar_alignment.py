"""Classical polar-alignment drift-rate approximation, used by
SimulatedPHD2Source to add a physically-motivated drift component driven by
a configurable polar alignment error, rather than only an abstract
constant/ramp/random-walk baseline.

IMPORTANT -- confidence level: the declination-drift formula below is the
well-established, widely cited first-order small-angle approximation from
classical drift-alignment theory (R.N. Hook, "Polar axis alignment
requirements of astronomical photography", J. Brit. Astron. Assoc. 99(1),
1989; elaborated by F. Barrett, "Determining Polar Axis Alignment
Accuracy"). The companion right-ascension-drift formula is this module's
own reconstruction from the same small-angle framework -- the reference
sources render their equations as images that couldn't be extracted
symbolically, so this was derived from the documented qualitative behavior
(zero at the celestial equator, growing without bound near the pole, in
quadrature with the declination-drift signal) plus dimensional consistency
with the declination formula, not transcribed verbatim from a primary
source. Treat it as a reasonable, physically-motivated approximation for
simulation purposes -- worth cross-checking against real logged behavior
(does the sign/magnitude pattern match as hour angle and declination
change?) before leaning on it for precise quantitative conclusions.

Model: a polar axis misaligned from the true pole by a small angle P
(commonly a few arcminutes for a careful alignment), in a direction
described by an "error angle" A (roughly, the hour angle at which the
error's effect on declination is maximal). As the true hour angle H
advances over the session (at the sidereal rate), a star at declination
delta that is genuinely fixed in RA/Dec appears -- to the misaligned mount
-- to drift:

    Dec drift rate  (arcsec/s) = omega * P * cos(H - A)
    RA  drift rate  (arcsec/s) = omega * P * sin(H - A) * tan(delta)

where omega = SIDEREAL_ARCSEC_PER_SEC and P is in radians. Only the RA
component feeds into this app's RightAscensionRate-based compensation;
the Dec component is exposed for completeness/diagnostics but isn't acted
on here (Dec drift is PHD2's own guiding's job, unaffected by this app).
"""

import math

from src.model.constants import SIDEREAL_ARCSEC_PER_SEC

ARCMIN_TO_RAD = math.pi / (180.0 * 60.0)


def polar_alignment_ra_drift_rate(polar_error_arcmin, polar_error_angle_deg,
                                   hour_angle_deg, declination_deg):
    """RA-axis drift rate (arcsec/s of real sky motion) caused by a polar
    alignment error of the given magnitude/direction, at the given hour
    angle and declination. Zero at the celestial equator; undefined exactly
    at the pole (tan(90 deg) blows up) -- callers should guard against
    declinations extremely close to +/-90 deg."""
    p_rad = polar_error_arcmin * ARCMIN_TO_RAD
    phase = math.radians(hour_angle_deg - polar_error_angle_deg)
    return SIDEREAL_ARCSEC_PER_SEC * p_rad * math.sin(phase) * math.tan(math.radians(declination_deg))


def polar_alignment_dec_drift_rate(polar_error_arcmin, polar_error_angle_deg, hour_angle_deg):
    """Dec-axis drift rate (arcsec/s) caused by the same polar alignment
    error -- not consumed elsewhere in this app (which only compensates
    RA), but exposed for diagnostics/documentation, and because it's the
    axis classical drift-alignment procedures actually measure."""
    p_rad = polar_error_arcmin * ARCMIN_TO_RAD
    phase = math.radians(hour_angle_deg - polar_error_angle_deg)
    return SIDEREAL_ARCSEC_PER_SEC * p_rad * math.cos(phase)
