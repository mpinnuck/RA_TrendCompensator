"""Rolling-window linear trend fit over RA raw-distance samples."""

import collections
import statistics
import time


class TrendEstimator:
    def __init__(self, window_seconds, min_samples_for_trend):
        self.window_seconds = window_seconds
        self.min_samples_for_trend = min_samples_for_trend
        self.samples = collections.deque()

    def add_sample(self, ra_raw_arcsec, timestamp=None):
        """timestamp lets the caller supply its own clock (e.g. a simulated,
        fast-forwarded clock) instead of the real wall clock -- defaults to
        time.time() to preserve existing behavior for the real PHD2 path."""
        now = timestamp if timestamp is not None else time.time()
        self.samples.append((now, ra_raw_arcsec))
        cutoff = now - self.window_seconds
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

    def reset(self):
        self.samples.clear()

    def fit_trend(self):
        """Returns (slope_arcsec_per_sec, n_samples); slope is None if insufficient data."""
        n = len(self.samples)
        if n < self.min_samples_for_trend:
            return None, n

        t0 = self.samples[0][0]
        xs = [t - t0 for t, _ in self.samples]
        ys = [v for _, v in self.samples]

        mean_x = statistics.mean(xs)
        mean_y = statistics.mean(ys)
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den = sum((x - mean_x) ** 2 for x in xs)
        if den == 0:
            return None, n

        slope = num / den
        return slope, n
