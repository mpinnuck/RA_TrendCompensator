"""Unit tests for GuideQualityMonitor -- moving RMS of raw RA deviation,
plus the trend (1st derivative) of that RMS over time."""

import pytest

from src.model.guide_quality_monitor import GuideQualityMonitor


def test_rms_reflects_magnitude_not_signed_average():
    # An oscillating +2/-2 signal averages to ~0 (looks like perfect
    # guiding) but should show a real RMS of 2.0 -- this is the whole
    # reason RMS is used instead of a plain moving average.
    monitor = GuideQualityMonitor(
        rms_window_seconds=100, rms_trend_window_seconds=1000, rms_sample_interval_seconds=1000
    )
    values = [2.0, -2.0, 2.0, -2.0, 2.0, -2.0]
    for i, v in enumerate(values):
        monitor.add_sample(timestamp=1000.0 + i, ra_raw_arcsec=v)

    assert monitor.current_rms == pytest.approx(2.0)


def test_rms_is_available_from_the_first_sample():
    monitor = GuideQualityMonitor(
        rms_window_seconds=100, rms_trend_window_seconds=1000, rms_sample_interval_seconds=1000
    )
    assert monitor.current_rms is None
    monitor.add_sample(timestamp=1000.0, ra_raw_arcsec=3.0)
    assert monitor.current_rms == pytest.approx(3.0)  # RMS of a single value is its magnitude


def test_old_samples_are_trimmed_from_the_rms_window():
    monitor = GuideQualityMonitor(
        rms_window_seconds=10, rms_trend_window_seconds=1000, rms_sample_interval_seconds=1000
    )
    monitor.add_sample(timestamp=1000.0, ra_raw_arcsec=10.0)  # will fall out of the window
    monitor.add_sample(timestamp=1005.0, ra_raw_arcsec=0.0)
    monitor.add_sample(timestamp=1020.0, ra_raw_arcsec=0.0)  # 20s later -- outside a 10s window

    # Only the last two samples should remain (both 0.0) -- the 10.0 outlier trimmed out.
    assert monitor.current_rms == pytest.approx(0.0)


def test_rms_trend_detects_improving_guiding():
    # Guiding error shrinking over time (each RMS sample smaller than the
    # last) should show a NEGATIVE trend slope.
    monitor = GuideQualityMonitor(
        rms_window_seconds=5, rms_trend_window_seconds=1000, rms_sample_interval_seconds=1
    )
    t = 1000.0
    for magnitude in [5.0, 5.0, 4.0, 4.0, 3.0, 3.0, 2.0, 2.0, 1.0, 1.0]:
        monitor.add_sample(timestamp=t, ra_raw_arcsec=magnitude)
        t += 1.0
        monitor.add_sample(timestamp=t, ra_raw_arcsec=-magnitude)
        t += 1.0

    slope, n = monitor.get_rms_trend()
    assert slope is not None
    assert slope < 0  # RMS shrinking -- guiding improving


def test_rms_trend_detects_worsening_guiding():
    monitor = GuideQualityMonitor(
        rms_window_seconds=5, rms_trend_window_seconds=1000, rms_sample_interval_seconds=1
    )
    t = 1000.0
    for magnitude in [1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 4.0, 5.0, 5.0]:
        monitor.add_sample(timestamp=t, ra_raw_arcsec=magnitude)
        t += 1.0
        monitor.add_sample(timestamp=t, ra_raw_arcsec=-magnitude)
        t += 1.0

    slope, n = monitor.get_rms_trend()
    assert slope is not None
    assert slope > 0  # RMS growing -- guiding getting worse


def test_reset_clears_both_rms_and_its_trend():
    monitor = GuideQualityMonitor(
        rms_window_seconds=100, rms_trend_window_seconds=1000, rms_sample_interval_seconds=1
    )
    for i in range(5):
        monitor.add_sample(timestamp=1000.0 + i, ra_raw_arcsec=2.0)
    assert monitor.current_rms is not None

    monitor.reset()

    assert monitor.current_rms is None
    slope, n = monitor.get_rms_trend()
    assert slope is None
