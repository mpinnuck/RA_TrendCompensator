"""Unit tests for DriftHistory -- rolling sample/rate-change buffers."""

import time

from src.model.drift_history import DriftHistory


def test_add_sample_and_snapshot():
    hist = DriftHistory(max_seconds=100)
    now = time.time()
    hist.add_sample(now, 1.0)
    hist.add_sample(now + 1, 2.0)

    samples, rate_changes = hist.snapshot()
    assert samples == [(now, 1.0), (now + 1, 2.0)]
    assert rate_changes == []


def test_old_samples_are_trimmed():
    hist = DriftHistory(max_seconds=10)
    now = time.time()
    hist.add_sample(now - 20, 1.0)  # older than the window -- should be trimmed
    hist.add_sample(now, 2.0)

    samples, _ = hist.snapshot()
    assert samples == [(now, 2.0)]


def test_rate_changes_tracked_independently_of_samples():
    hist = DriftHistory(max_seconds=100)
    now = time.time()
    hist.add_sample(now, 1.0)
    hist.add_rate_change(now, 0.05)

    samples, rate_changes = hist.snapshot()
    assert samples == [(now, 1.0)]
    assert rate_changes == [(now, 0.05)]


def test_snapshot_returns_independent_copies():
    hist = DriftHistory(max_seconds=100)
    hist.add_sample(time.time(), 1.0)

    samples, _ = hist.snapshot()
    samples.append((0, 999))  # mutate the returned list

    samples_again, _ = hist.snapshot()
    assert len(samples_again) == 1  # internal buffer untouched
