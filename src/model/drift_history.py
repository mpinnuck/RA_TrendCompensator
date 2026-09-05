"""Thread-safe rolling buffers of RA drift samples and RA-rate-change events,
both trimmed to a rolling wall-clock window.

Written to from the PHD2/mount worker thread (via the ViewModel), read from
the Tk main thread by the drift chart -- snapshot() returns plain-list copies
so the two threads never touch the same deque at once.
"""

import collections
import threading


class DriftHistory:
    def __init__(self, max_seconds):
        self.max_seconds = max_seconds
        self._lock = threading.Lock()
        self._samples = collections.deque()       # (timestamp, ra_raw_arcsec)
        self._rate_changes = collections.deque()   # (timestamp, new_offset)

    def add_sample(self, timestamp, value):
        with self._lock:
            self._samples.append((timestamp, value))
            self._trim(self._samples, timestamp)

    def add_rate_change(self, timestamp, value):
        with self._lock:
            self._rate_changes.append((timestamp, value))
            self._trim(self._rate_changes, timestamp)

    def _trim(self, buf, now):
        cutoff = now - self.max_seconds
        while buf and buf[0][0] < cutoff:
            buf.popleft()

    def snapshot(self):
        """Returns (samples, rate_changes) as plain lists -- safe to hand to the View."""
        with self._lock:
            return list(self._samples), list(self._rate_changes)
