"""Unit tests for TrendEstimator, focused on the explicit-timestamp option
added to support simulation mode's own (fast-forwardable) clock."""

import time

import pytest

from src.model.trend_estimator import TrendEstimator


def test_add_sample_defaults_to_real_time():
    trend = TrendEstimator(window_seconds=100, min_samples_for_trend=2)
    before = time.time()
    trend.add_sample(1.0)
    after = time.time()
    ts, value = trend.samples[0]
    assert before <= ts <= after
    assert value == 1.0


def test_add_sample_uses_explicit_timestamp_when_given():
    trend = TrendEstimator(window_seconds=100, min_samples_for_trend=2)
    trend.add_sample(1.0, timestamp=1000.0)
    trend.add_sample(2.0, timestamp=1010.0)
    assert list(trend.samples) == [(1000.0, 1.0), (1010.0, 2.0)]


def test_explicit_timestamps_are_trimmed_by_the_same_window():
    trend = TrendEstimator(window_seconds=10, min_samples_for_trend=1)
    trend.add_sample(1.0, timestamp=1000.0)
    trend.add_sample(2.0, timestamp=1020.0)  # 20s later -- outside a 10s window
    assert list(trend.samples) == [(1020.0, 2.0)]


def test_fit_trend_recovers_a_known_slope_with_explicit_timestamps():
    trend = TrendEstimator(window_seconds=1000, min_samples_for_trend=2)
    for i in range(10):
        trend.add_sample(i * 0.5, timestamp=1000.0 + i * 2.0)  # slope = 0.5/2.0 = 0.25 arcsec/s

    slope, n = trend.fit_trend()
    assert n == 10
    assert slope == pytest.approx(0.25)
