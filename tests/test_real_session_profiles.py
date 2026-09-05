"""Sanity checks on the real, log-derived drift profiles in
real_session_profiles.py -- shape-level assertions, not exact-value
fragile tests, since the numbers themselves are transcribed from a chart
in another conversation (see that module's docstring for derivation)."""

from src.model.real_session_profiles import NGC6744_2026_09_03, PROFILES


def test_profile_is_registered():
    assert "NGC6744_2026_09_03" in PROFILES
    assert PROFILES["NGC6744_2026_09_03"] == NGC6744_2026_09_03


def test_profile_points_are_sorted_by_elapsed_time():
    times = [t for t, _ in NGC6744_2026_09_03]
    assert times == sorted(times)


def test_profile_starts_near_zero_and_climbs_later():
    # Matches the real session: flat/mixed for the first ~50 minutes
    # (pre meridian-flip), then a sustained climb.
    early_rates = [r for t, r in NGC6744_2026_09_03 if t <= 3120]
    late_rates = [r for t, r in NGC6744_2026_09_03 if t > 7000]

    assert max(abs(r) for r in early_rates) < 0.07
    assert min(late_rates) > 0.14
