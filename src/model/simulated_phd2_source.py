"""Closed-loop synthetic PHD2 GuideStep source for simulation mode.

Same public interface as PHD2Client (start/stop, emits GuideStep-shaped
dicts via on_guide_step), but generates data instead of reading a socket --
so the whole app can be exercised and tuned with no PHD2 instance and no
mount connected.

The model:
  - A "true" underlying uncompensated tracking-rate error (arcsec/s) that
    the ViewModel is trying to null out. It's the sum of up to two parts:
      1. A baseline from one of:
           * a constant (true_drift_arcsec_per_sec) that can optionally
             ramp linearly over the session (drift_ramp_arcsec_per_sec_per_hour), or
           * a drift_profile -- (elapsed_seconds, rate_arcsec_per_sec)
             points, piecewise-linearly interpolated -- for replaying the
             actual *shape* of a real observed session (see
             real_session_profiles.py). Takes priority over the constant/ramp.
      2. A polar-alignment-error-driven component (see polar_alignment.py),
         computed from the configured error magnitude/direction, the
         current simulated hour angle (which advances at the sidereal rate
         from start_hour_angle_hours as the session runs), and declination.
         This is additive on top of (1), not a replacement for it.
    A slow random walk (drift_walk_std) is layered on top of the total.
  - Each tick, we read back whatever RightAscensionRate the ViewModel has
    currently applied (via get_applied_rate, converted to arcsec/s) and
    subtract it from the true drift rate to get the *residual* -- the part
    still uncompensated.
  - The residual rate is integrated into a raw RA error value (plus a small
    long-term pull-to-zero so it doesn't wander unbounded over an 8-hour
    run, and per-step noise for realism).

This is deliberately the same relationship the app's own TrendEstimator
assumes (slope of raw RA error ~= uncompensated rate, in arcsec/s): as the
compensator's applied offset converges on the true drift rate, the residual
-- and therefore the trend the app measures -- genuinely flattens out.

Declination matters here too: ASCOM's RightAscensionRate is in RA-time-
seconds per sidereal second, not arcsec/s -- one RA-second is only 15.041"
of real sky motion at the celestial equator, scaled by cos(dec) elsewhere.
get_declination lets this conversion match whatever the ViewModel itself
uses, so the closed loop stays physically self-consistent away from dec=0.

Sign convention: which physical sky direction maps to a positive
RADistanceRaw is entirely determined by a real rig's camera orientation
and PHD2 calibration -- it isn't a fixed astronomical convention, so the
simulator can't derive it from first principles. bias_direction ("west" or
"east") is the single source of truth for sign: true_drift_arcsec_per_sec
and drift_ramp_arcsec_per_sec_per_hour are treated as MAGNITUDES (their
own sign is ignored) and given the sign matching bias_direction. "west" is
positive by convention here, matching how the real NGC 6744 profile's
numbers are already signed (see real_session_profiles.py) -- so loading
that profile and leaving bias_direction at its "west" default stay
consistent with each other. drift_profile is unaffected by this setting,
since a profile's numbers are already correctly signed from real data.
"""

import math
import random
import threading
import time

from src.model.constants import HOUR_ANGLE_DEG_PER_SEC, SIDEREAL_ARCSEC_PER_SEC
from src.model.polar_alignment import polar_alignment_ra_drift_rate


class SimulatedPHD2Source:
    def __init__(self, get_applied_rate, get_declination, on_guide_step, on_guiding_stopped,
                 on_app_state, logger, pixel_scale_arcsec, true_drift_arcsec_per_sec, drift_walk_std,
                 drift_ramp_arcsec_per_sec_per_hour, noise_arcsec,
                 pull_to_zero_per_step, guide_step_interval_s, speed_multiplier,
                 drift_profile=None,
                 target_name="", target_ra_hours=0.0, start_hour_angle_hours=0.0,
                 polar_error_arcmin=0.0, polar_error_angle_deg=0.0,
                 bias_direction="west"):
        self.get_applied_rate = get_applied_rate
        self.get_declination = get_declination
        self.on_guide_step = on_guide_step
        self.on_guiding_stopped = on_guiding_stopped
        self.on_app_state = on_app_state
        self.logger = logger

        self.pixel_scale_arcsec = pixel_scale_arcsec
        self.drift_walk_std = drift_walk_std
        self.noise_arcsec = noise_arcsec
        self.pull_to_zero_per_step = pull_to_zero_per_step
        self.guide_step_interval_s = guide_step_interval_s
        self.speed_multiplier = max(speed_multiplier, 0.01)

        self.target_name = target_name
        self.target_ra_hours = target_ra_hours
        self.start_hour_angle_hours = start_hour_angle_hours
        self.polar_error_arcmin = polar_error_arcmin
        self.polar_error_angle_deg = polar_error_angle_deg
        self.bias_direction = bias_direction
        bias_sign = -1.0 if bias_direction == "east" else 1.0

        # Profile path: sorted (elapsed_seconds, rate) points, held constant
        # before the first and after the last point.
        self.drift_profile = sorted(drift_profile) if drift_profile else None
        self._true_drift_arcsec_per_sec = abs(true_drift_arcsec_per_sec) * bias_sign
        # Per-tick increment to the true drift rate from the linear ramp,
        # converted from arcsec/s per hour into arcsec/s per tick. Only
        # used when no profile is active.
        self._drift_ramp_per_step = abs(drift_ramp_arcsec_per_sec_per_hour) * bias_sign / 3600.0 * guide_step_interval_s

        self._elapsed_seconds = 0.0
        self._walk_perturbation = 0.0
        self._true_drift_rate = self._true_drift_arcsec_per_sec  # current baseline + perturbation
        self._hour_angle_deg = start_hour_angle_hours * 15.0
        self._raw_error = 0.0
        self._sim_now = None  # set in start(); advances by guide_step_interval_s per tick

        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._sim_now = time.time()
        mode = f"profile ({len(self.drift_profile)} points)" if self.drift_profile else "constant/ramp"
        target = f"{self.target_name} " if self.target_name else ""
        self.logger(f"[SIM] Starting simulated PHD2 feed -- target {target}"
                    f"(start HA={self.start_hour_angle_hours:+.2f}h), drift model: {mode} "
                    f"(bias direction: {self.bias_direction}), "
                    f"polar error {self.polar_error_arcmin:.1f}' @ {self.polar_error_angle_deg:.0f} deg, "
                    f"step {self.guide_step_interval_s}s @ {self.speed_multiplier}x.")
        self.on_app_state("Guiding")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.on_guiding_stopped()

    def _run(self):
        while not self._stop.is_set():
            self.tick()
            time.sleep(self.guide_step_interval_s / self.speed_multiplier)

    def _interpolate_profile(self, elapsed_seconds):
        points = self.drift_profile
        if elapsed_seconds <= points[0][0]:
            return points[0][1]
        if elapsed_seconds >= points[-1][0]:
            return points[-1][1]
        for (t0, r0), (t1, r1) in zip(points, points[1:]):
            if t0 <= elapsed_seconds <= t1:
                frac = (elapsed_seconds - t0) / (t1 - t0)
                return r0 + frac * (r1 - r0)
        return points[-1][1]  # unreachable given the bounds checks above

    def tick(self):
        """Advances the simulation by one guide step and emits it. Exposed
        as a public method (rather than folded into _run) so tests can
        drive it deterministically without threading.

        The simulated clock (SimTimestamp) always advances by exactly
        guide_step_interval_s per tick, regardless of how quickly real
        ticks actually fire -- so TrendEstimator's slope (computed from
        these timestamps) stays in true arcsec-per-second units, matching
        what the physics below assumes, even when speed_multiplier makes
        ticks arrive faster than real time. Hour angle advances the same
        way, so a polar-alignment-driven drift responds to simulated
        session time, not wall-clock time."""
        if self._sim_now is None:
            self._sim_now = time.time()
        self._sim_now += self.guide_step_interval_s
        self._elapsed_seconds += self.guide_step_interval_s
        self._hour_angle_deg += HOUR_ANGLE_DEG_PER_SEC * self.guide_step_interval_s

        self._walk_perturbation += random.gauss(0, self.drift_walk_std)

        if self.drift_profile:
            baseline = self._interpolate_profile(self._elapsed_seconds)
        else:
            self._true_drift_arcsec_per_sec += self._drift_ramp_per_step
            baseline = self._true_drift_arcsec_per_sec

        dec_deg = self.get_declination()
        if self.polar_error_arcmin and dec_deg is not None:
            baseline += polar_alignment_ra_drift_rate(
                self.polar_error_arcmin, self.polar_error_angle_deg, self._hour_angle_deg, dec_deg
            )

        self._true_drift_rate = baseline + self._walk_perturbation

        cos_dec = math.cos(math.radians(dec_deg)) if dec_deg is not None else 1.0
        applied_rate_arcsec_per_sec = self.get_applied_rate() * SIDEREAL_ARCSEC_PER_SEC * cos_dec
        residual_rate = self._true_drift_rate - applied_rate_arcsec_per_sec

        self._raw_error += residual_rate * self.guide_step_interval_s
        self._raw_error *= (1.0 - self.pull_to_zero_per_step)
        self._raw_error += random.gauss(0, self.noise_arcsec)

        ra_raw_px = self._raw_error / self.pixel_scale_arcsec
        self.on_guide_step({"RADistanceRaw": ra_raw_px, "SimTimestamp": self._sim_now})
