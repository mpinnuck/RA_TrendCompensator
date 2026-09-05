"""Unit tests for SimulatedPHD2Source -- the synthetic, closed-loop drift
model used by simulation mode. Randomness is zeroed out (drift_walk_std=0,
noise_arcsec=0) so the core relationship -- residual rate in, raw error out
-- can be checked deterministically."""

import pytest

from src.model.constants import SIDEREAL_ARCSEC_PER_SEC
from src.model.simulated_phd2_source import SimulatedPHD2Source


def _make_source(get_applied_rate, true_drift_arcsec_per_sec=0.0, pull_to_zero_per_step=0.0,
                  drift_ramp_arcsec_per_sec_per_hour=0.0, drift_profile=None, get_declination=None,
                  start_hour_angle_hours=0.0, polar_error_arcmin=0.0, polar_error_angle_deg=0.0,
                  bias_direction="west"):
    events = []
    return SimulatedPHD2Source(
        get_applied_rate=get_applied_rate,
        get_declination=get_declination or (lambda: 0.0),
        on_guide_step=events.append,
        on_guiding_stopped=lambda: None,
        on_app_state=lambda state: None,
        logger=lambda msg: None,
        pixel_scale_arcsec=0.5,
        true_drift_arcsec_per_sec=true_drift_arcsec_per_sec,
        drift_walk_std=0.0,
        drift_ramp_arcsec_per_sec_per_hour=drift_ramp_arcsec_per_sec_per_hour,
        noise_arcsec=0.0,
        pull_to_zero_per_step=pull_to_zero_per_step,
        guide_step_interval_s=2.0,
        speed_multiplier=1.0,
        drift_profile=drift_profile,
        start_hour_angle_hours=start_hour_angle_hours,
        polar_error_arcmin=polar_error_arcmin,
        polar_error_angle_deg=polar_error_angle_deg,
        bias_direction=bias_direction,
    ), events


def test_tick_emits_guide_step_shaped_messages():
    source, events = _make_source(get_applied_rate=lambda: 0.0, true_drift_arcsec_per_sec=0.05)
    source.tick()
    assert len(events) == 1
    assert "RADistanceRaw" in events[0]
    assert isinstance(events[0]["RADistanceRaw"], float)


def test_uncompensated_drift_grows_the_raw_error():
    # No correction ever applied -- residual rate stays at the full true drift.
    source, events = _make_source(get_applied_rate=lambda: 0.0, true_drift_arcsec_per_sec=0.05)
    for _ in range(20):
        source.tick()

    values = [e["RADistanceRaw"] for e in events]
    # Same sign as the true drift throughout, and growing in magnitude.
    assert all(v > 0 for v in values)
    assert values[-1] > values[len(values) // 2] > values[0]


def test_perfect_compensation_keeps_raw_error_near_zero():
    # Applied rate exactly cancels the true drift rate every tick.
    true_drift = 0.05
    applied_rate = true_drift / SIDEREAL_ARCSEC_PER_SEC
    source, events = _make_source(get_applied_rate=lambda: applied_rate, true_drift_arcsec_per_sec=true_drift)

    for _ in range(50):
        source.tick()

    values = [e["RADistanceRaw"] for e in events]
    assert all(abs(v) < 1e-6 for v in values)


def test_pull_to_zero_bounds_long_term_wander():
    # With a nonzero pull-to-zero term, a sustained uncompensated drift
    # settles to a bounded steady state rather than growing forever.
    # Recurrence: x[n+1] = (x[n] + residual*dt) * (1-p)
    # Steady state: x* = residual*dt*(1-p) / p
    residual = 0.05
    dt = 2.0
    p = 0.05
    expected_steady_state = residual * dt * (1 - p) / p

    source, events = _make_source(
        get_applied_rate=lambda: 0.0, true_drift_arcsec_per_sec=residual, pull_to_zero_per_step=p
    )
    for _ in range(500):
        source.tick()

    final_raw_error = events[-1]["RADistanceRaw"] * 0.5  # convert back from pixels (pixel_scale_arcsec=0.5)
    assert final_raw_error == pytest.approx(expected_steady_state, rel=1e-3)


def test_drift_ramp_makes_raw_error_grow_faster_over_time():
    # No correction applied, no base drift or noise -- only the ramp is
    # driving the true rate upward, so successive raw-error increments
    # (the effective instantaneous rate) should themselves keep growing.
    source, events = _make_source(
        get_applied_rate=lambda: 0.0,
        true_drift_arcsec_per_sec=0.0,
        drift_ramp_arcsec_per_sec_per_hour=36.0,  # 0.01 arcsec/s per second, i.e. per 2s tick: 0.02 arcsec/s
    )
    for _ in range(20):
        source.tick()

    values = [e["RADistanceRaw"] for e in events]
    deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    # Each successive step's increment should be larger than the last --
    # the signature of an accelerating (ramping) drift rate.
    assert all(deltas[i + 1] > deltas[i] for i in range(len(deltas) - 1))


def test_polar_error_is_off_by_default():
    # No polar error configured (default 0) -- hour angle progressing over
    # many ticks should have no effect on the raw error at all.
    source, events = _make_source(get_applied_rate=lambda: 0.0)
    for _ in range(50):
        source.tick()
    assert all(v == 0.0 for v in [e["RADistanceRaw"] for e in events])


def test_polar_error_feeds_into_the_true_drift_rate():
    # A nonzero polar error at a non-equatorial declination, away from the
    # error angle, should produce a nonzero true drift rate even with no
    # other baseline configured.
    source, events = _make_source(
        get_applied_rate=lambda: 0.0,
        get_declination=lambda: -45.0,
        start_hour_angle_hours=1.0,  # HA = 15 deg at t=0, away from error angle 0
        polar_error_arcmin=5.0,
        polar_error_angle_deg=0.0,
    )
    source.tick()
    assert source._true_drift_rate != 0.0
    assert events[0]["RADistanceRaw"] != 0.0


def test_bias_direction_only_controls_sign_not_magnitude():
    # Same numeric magnitude entered either way -- west should give the
    # mirror image of east, confirming the direction setting is the sole
    # source of sign and the magnitude fields are direction-agnostic.
    source_west, events_west = _make_source(
        get_applied_rate=lambda: 0.0, true_drift_arcsec_per_sec=0.05, bias_direction="west"
    )
    source_east, events_east = _make_source(
        get_applied_rate=lambda: 0.0, true_drift_arcsec_per_sec=0.05, bias_direction="east"
    )
    for _ in range(10):
        source_west.tick()
        source_east.tick()

    west_values = [e["RADistanceRaw"] for e in events_west]
    east_values = [e["RADistanceRaw"] for e in events_east]
    assert all(w == pytest.approx(-e) for w, e in zip(west_values, east_values))


def test_bias_direction_ignores_the_sign_of_the_entered_magnitude():
    # A negative number typed into a magnitude field shouldn't produce a
    # third distinct behavior -- direction is authoritative either way.
    source_pos, events_pos = _make_source(
        get_applied_rate=lambda: 0.0, true_drift_arcsec_per_sec=0.05, bias_direction="west"
    )
    source_neg, events_neg = _make_source(
        get_applied_rate=lambda: 0.0, true_drift_arcsec_per_sec=-0.05, bias_direction="west"
    )
    source_pos.tick()
    source_neg.tick()
    assert events_pos[0]["RADistanceRaw"] == pytest.approx(events_neg[0]["RADistanceRaw"])


def test_drift_profile_returns_exact_values_at_breakpoints():
    profile = [(0, 0.01), (10, 0.05), (20, -0.02)]
    source, _ = _make_source(get_applied_rate=lambda: 0.0, drift_profile=profile)

    assert source._interpolate_profile(0) == pytest.approx(0.01)
    assert source._interpolate_profile(10) == pytest.approx(0.05)
    assert source._interpolate_profile(20) == pytest.approx(-0.02)


def test_drift_profile_interpolates_linearly_between_points():
    profile = [(0, 0.0), (10, 1.0)]
    source, _ = _make_source(get_applied_rate=lambda: 0.0, drift_profile=profile)

    assert source._interpolate_profile(5) == pytest.approx(0.5)
    assert source._interpolate_profile(2.5) == pytest.approx(0.25)


def test_drift_profile_holds_constant_outside_its_range():
    profile = [(10, 0.1), (20, 0.2)]
    source, _ = _make_source(get_applied_rate=lambda: 0.0, drift_profile=profile)

    assert source._interpolate_profile(0) == pytest.approx(0.1)   # before first point
    assert source._interpolate_profile(1000) == pytest.approx(0.2)  # after last point


def test_drift_profile_drives_the_true_drift_rate_over_ticks():
    # guide_step_interval_s=2.0, so ticks land at elapsed=2,4,6,8,10
    profile = [(0, 0.0), (10, 1.0)]  # linear ramp from 0.0 to 1.0 over 10s
    source, events = _make_source(get_applied_rate=lambda: 0.0, drift_profile=profile)

    for _ in range(5):
        source.tick()

    assert source._true_drift_rate == pytest.approx(1.0)  # elapsed=10, end of profile
    assert len(events) == 5
