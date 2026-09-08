"""CSV data logging for empirically determining raDrift = f(mount RArate)
on a specific rig from a live run.

The human-readable text log (ViewModel._log) is fine to read, but painful
to analyze quantitatively -- pulling (applied rate, measured drift) pairs
back out means regex-parsing free-text lines. This writes one structured
CSV instead, alongside the text log, with every guide step and every
trend-fit/adjustment cycle interleaved in the same file, in real time
order -- an "event_type" column ("guide_step" or "adjustment")
distinguishes the two row shapes, which share one column set (unused
columns are left blank per row). Keeping both event types in one file
means the actual chronological sequence -- which guide steps happened
between which adjustments -- is preserved directly, without needing to
merge two separately-timestamped files back together afterwards.

Row shapes:
  - guide_step: one row per PHD2 guide step -- the finest-grained record
    (raw angular error, whatever RA rate was applied at that moment,
    declination). Enough on its own to derive drift rate over any custom
    time window, if the app's own windowing isn't what you want.
  - adjustment: one row per trend-fit/adjustment cycle -- the app's own
    computed (rate that was applied over the window, drift measured over
    that window) pairs, ready to use directly.

IMPORTANT for calibration: previous_ra_rate in an adjustment row is only
the rate that was ACTUALLY applied to the physical mount if dry_run was
False for that row -- check the dry_run column. With dry_run True, the
mount's real rate wasn't touched, so the measured slope reflects whatever
rate (if any) was really active, not previous_ra_rate.

The file is appended to (never truncated) so data can accumulate across
multiple sessions; the header row is written once, the first time the
file is created or found empty.
"""

import csv
import os


def _fallback_log_dir():
    for env_var in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOME"):
        value = os.environ.get(env_var)
        if value:
            return value
    return os.path.expanduser("~")


class DataLogger:
    FIELDS = [
        "event_type", "timestamp", "elapsed_seconds",
        "declination_deg", "side_of_pier", "dry_run",
        # guide_step rows:
        "ra_raw_arcsec", "applied_ra_rate", "phd2_avg_dist_arcsec",
        # adjustment rows:
        "previous_ra_rate", "slope_arcsec_per_sec", "n_samples", "cos_dec",
        "needed_offset_increment", "damping_factor", "delta_applied", "new_ra_rate",
    ]

    def __init__(self, csv_path):
        self.csv_path = csv_path
        self._ensure_writable_path()
        self._ensure_header()

    def _fallback_path(self):
        fallback_dir = os.path.join(_fallback_log_dir(), "RA_TrendCompensator")
        os.makedirs(fallback_dir, exist_ok=True)
        return os.path.join(fallback_dir, os.path.basename(self.csv_path))

    def _is_writable_dir(self, directory):
        try:
            if not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
            return os.access(directory, os.W_OK)
        except OSError:
            return False

    def _ensure_writable_path(self):
        directory = os.path.dirname(os.path.abspath(self.csv_path)) or os.getcwd()
        if not self._is_writable_dir(directory):
            self.csv_path = self._fallback_path()

    def _ensure_header(self):
        try:
            needs_header = not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0
            if needs_header:
                with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(self.FIELDS)
            return
        except OSError:
            self.csv_path = self._fallback_path()
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(self.FIELDS)

    def log_guide_step(self, **kwargs):
        self._append(event_type="guide_step", **kwargs)

    def log_adjustment(self, **kwargs):
        self._append(event_type="adjustment", **kwargs)

    def _append(self, **values):
        try:
            if not self._is_writable_dir(os.path.dirname(os.path.abspath(self.csv_path)) or os.getcwd()):
                self.csv_path = self._fallback_path()
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([values.get(field, "") for field in self.FIELDS])
        except OSError:
            self.csv_path = self._fallback_path()
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([values.get(field, "") for field in self.FIELDS])
