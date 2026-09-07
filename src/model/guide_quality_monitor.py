"""Tracks recent guiding quality (RMS of raw RA deviation) and whether it's
improving or getting worse over time -- a meta-diagnostic distinct from the
trend used to drive RA rate corrections.

Why RMS and not a plain moving average of the signed deviation: a plain
average can badly mislead -- a star oscillating +2", -2", +2", -2" every
step averages to ~0, which looks like perfect guiding when it's actually
quite poor. RMS reflects the magnitude of scatter regardless of sign, which
is the standard metric for this in the guiding community (it's what PHD2
itself reports as guide error).

Two windows, two purposes:
  - rms_window_seconds: how much recent raw-deviation history the current
    RMS figure is computed over (a short-ish window, e.g. 5 minutes, so it
    reflects "how's guiding doing right now").
  - rms_trend_window_seconds: a separate, longer window over which
    periodically-sampled RMS values themselves are fit with a linear trend
    (reusing TrendEstimator) -- this is the "1st derivative": a negative
    slope means RMS is shrinking over the session (the compensator appears
    to be helping); positive means it's growing (not helping, or hurting).
"""

import collections
import math

from src.model.trend_estimator import TrendEstimator


class GuideQualityMonitor:
    def __init__(self, rms_window_seconds, rms_trend_window_seconds, rms_sample_interval_seconds):
        self.rms_window_seconds = rms_window_seconds
        self.rms_sample_interval_seconds = rms_sample_interval_seconds

        self._raw_samples = collections.deque()  # (timestamp, ra_raw_arcsec)
        self._last_rms_sample_time = None
        # Reuses TrendEstimator's linear-regression machinery, just fed a
        # stream of periodically-sampled RMS values instead of raw error.
        self._rms_trend = TrendEstimator(rms_trend_window_seconds, min_samples_for_trend=3)
        self.current_rms = None

    def add_sample(self, timestamp, ra_raw_arcsec):
        self._raw_samples.append((timestamp, ra_raw_arcsec))
        cutoff = timestamp - self.rms_window_seconds
        while self._raw_samples and self._raw_samples[0][0] < cutoff:
            self._raw_samples.popleft()

        # At least the sample just appended survives trimming (its own
        # timestamp can't be older than a cutoff derived from itself), so
        # this always recomputes from live window contents -- no stale
        # value left over from before older samples aged out.
        self.current_rms = self._compute_rms()

        if self.current_rms is not None and (
            self._last_rms_sample_time is None
            or timestamp - self._last_rms_sample_time >= self.rms_sample_interval_seconds
        ):
            self._rms_trend.add_sample(self.current_rms, timestamp)
            self._last_rms_sample_time = timestamp

    def _compute_rms(self):
        values = [v for _, v in self._raw_samples]
        mean_sq = sum(v * v for v in values) / len(values)
        return math.sqrt(mean_sq)

    def get_rms_trend(self):
        """Returns (slope_arcsec_per_sec, n_samples) for how the RMS itself
        is changing over time -- negative = improving, positive = getting
        worse. slope is None if there aren't enough RMS samples yet."""
        return self._rms_trend.fit_trend()

    def reset(self):
        self._raw_samples.clear()
        self._rms_trend.reset()
        self._last_rms_sample_time = None
        self.current_rms = None
