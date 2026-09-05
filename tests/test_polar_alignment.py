"""Unit tests for the polar-alignment drift-rate formulas.

See polar_alignment.py's module docstring for the confidence caveat on the
RA-drift formula: the declination-drift formula is a well-established
classical result; the RA-drift companion is this module's own
reconstruction from documented qualitative behavior, not a formula
transcribed verbatim from a primary source. These tests check the
qualitative/structural properties that ARE well-documented (zero at the
equator, growing near the pole, sign behavior with hour angle), which is
the level of confidence the formula actually warrants -- real validation
is a job for a dry run against the actual mount/PHD2, not this simulator.
"""

import pytest

from src.model.polar_alignment import polar_alignment_dec_drift_rate, polar_alignment_ra_drift_rate


def test_ra_drift_is_zero_at_the_celestial_equator():
    for hour_angle in [0, 30, 90, 145, 270]:
        rate = polar_alignment_ra_drift_rate(
            polar_error_arcmin=5.0, polar_error_angle_deg=0.0,
            hour_angle_deg=hour_angle, declination_deg=0.0
        )
        assert rate == pytest.approx(0.0, abs=1e-12)


def test_ra_drift_is_zero_when_hour_angle_equals_error_angle():
    # sin(H - A) = 0 when H == A, regardless of declination.
    rate = polar_alignment_ra_drift_rate(
        polar_error_arcmin=5.0, polar_error_angle_deg=40.0,
        hour_angle_deg=40.0, declination_deg=-63.8
    )
    assert rate == pytest.approx(0.0, abs=1e-12)


def test_ra_drift_scales_linearly_with_polar_error_magnitude():
    rate_1 = polar_alignment_ra_drift_rate(1.0, 0.0, hour_angle_deg=45.0, declination_deg=-45.0)
    rate_5 = polar_alignment_ra_drift_rate(5.0, 0.0, hour_angle_deg=45.0, declination_deg=-45.0)
    assert rate_5 == pytest.approx(rate_1 * 5.0)


def test_ra_drift_grows_approaching_the_pole():
    # tan(dec) grows without bound near +/-90 deg -- the magnitude of the
    # RA-drift term should grow correspondingly for a fixed error/HA.
    rate_moderate = abs(polar_alignment_ra_drift_rate(5.0, 0.0, hour_angle_deg=45.0, declination_deg=-45.0))
    rate_high = abs(polar_alignment_ra_drift_rate(5.0, 0.0, hour_angle_deg=45.0, declination_deg=-80.0))
    assert rate_high > rate_moderate


def test_ra_drift_flips_sign_across_the_error_angle():
    before = polar_alignment_ra_drift_rate(5.0, 0.0, hour_angle_deg=-10.0, declination_deg=-45.0)
    after = polar_alignment_ra_drift_rate(5.0, 0.0, hour_angle_deg=10.0, declination_deg=-45.0)
    assert before < 0 < after or after < 0 < before


def test_dec_drift_is_maximal_at_the_error_angle():
    at_error_angle = polar_alignment_dec_drift_rate(5.0, polar_error_angle_deg=30.0, hour_angle_deg=30.0)
    away_from_it = polar_alignment_dec_drift_rate(5.0, polar_error_angle_deg=30.0, hour_angle_deg=90.0)
    assert abs(at_error_angle) > abs(away_from_it)


def test_dec_drift_is_zero_in_quadrature_with_the_error_angle():
    rate = polar_alignment_dec_drift_rate(5.0, polar_error_angle_deg=0.0, hour_angle_deg=90.0)
    assert rate == pytest.approx(0.0, abs=1e-12)


def test_zero_polar_error_gives_zero_drift_on_both_axes():
    ra_rate = polar_alignment_ra_drift_rate(0.0, 0.0, hour_angle_deg=45.0, declination_deg=-45.0)
    dec_rate = polar_alignment_dec_drift_rate(0.0, 0.0, hour_angle_deg=45.0)
    assert ra_rate == 0.0
    assert dec_rate == 0.0
