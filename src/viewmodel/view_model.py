"""ViewModel: owns the model objects, exposes thread-safe log/state to the View."""

import math
import queue
import time
from datetime import datetime

from src.config import save_config
from src.model.constants import SIDEREAL_ARCSEC_PER_SEC
from src.model.data_logger import DataLogger
from src.model.mount_controller import MountController
from src.model.phd2_client import PHD2Client
from src.model.simulated_mount import SimulatedMountController
from src.model.simulated_phd2_source import SimulatedPHD2Source
from src.model.trend_estimator import TrendEstimator
from src.model.drift_history import DriftHistory

# Below this, cos(dec) is small enough that a tiny slope estimate translates
# into a huge RightAscensionRate value -- treat it as "declination unknown /
# unsafe to correct" and skip the adjustment rather than blow up. This is
# ~89.4 degrees -- no real imaging target sits this close to the pole.
MIN_COS_DEC = 0.01


class RATrendCompensatorViewModel:
    def __init__(self, config):
        self.config = config
        self.log_queue = queue.Queue()
        self.running = False

        self._build_models(config)

        self.dry_run = config["dry_run"]
        self.current_offset = 0.0
        self.last_side_of_pier = None
        self.last_apply_time = 0.0
        self.session_start_time = None

    # -- model construction ---------------------------------------------

    def _build_models(self, config):
        """(Re)creates the model objects from a config dict. Called at init,
        and again from update_config() when Settings are changed -- the
        connection details (host/port/prog id) and trend/chart parameters
        are only read at construction time, so applying new values means
        building fresh instances.

        When simulation_mode is on, the mount and PHD2 source are swapped
        for synthetic, closed-loop stand-ins (see src/model/simulated_*.py)
        so the rest of the pipeline runs unmodified with no hardware."""
        if config.get("simulation_mode", False):
            self.mount = SimulatedMountController(
                config["max_rate_magnitude"], self._log, declination_deg=config["sim_declination_deg"]
            )
            self.phd2 = SimulatedPHD2Source(
                get_applied_rate=self.mount.get_ra_rate,
                get_declination=self.mount.get_declination,
                on_guide_step=self._on_guide_step,
                on_guiding_stopped=self._on_guiding_stopped,
                on_app_state=self._on_app_state,
                logger=self._log,
                pixel_scale_arcsec=config["pixel_scale_arcsec"],
                true_drift_arcsec_per_sec=config["sim_true_drift_arcsec_per_sec"],
                drift_walk_std=config["sim_drift_walk_std"],
                drift_ramp_arcsec_per_sec_per_hour=config["sim_drift_ramp_arcsec_per_sec_per_hour"],
                drift_profile=config.get("sim_drift_profile"),
                noise_arcsec=config["sim_noise_arcsec"],
                pull_to_zero_per_step=config["sim_pull_to_zero_per_step"],
                guide_step_interval_s=config["sim_guide_step_interval_s"],
                speed_multiplier=config["sim_speed_multiplier"],
                target_name=config["sim_target_name"],
                target_ra_hours=config["sim_target_ra_hours"],
                start_hour_angle_hours=config["sim_start_hour_angle_hours"],
                polar_error_arcmin=config["sim_polar_error_arcmin"],
                polar_error_angle_deg=config["sim_polar_error_angle_deg"],
                bias_direction=config["sim_bias_direction"],
            )
            self._log("Simulation mode active -- using synthetic PHD2/mount data.")
        else:
            self.mount = MountController(
                config["ascom_prog_id"], config["max_rate_magnitude"], self._log
            )
            self.phd2 = PHD2Client(
                config["phd2_host"], config["phd2_port"],
                on_guide_step=self._on_guide_step,
                on_guiding_stopped=self._on_guiding_stopped,
                on_app_state=self._on_app_state,
                logger=self._log,
            )

        self.trend = TrendEstimator(config["window_seconds"], config["min_samples_for_trend"])
        self.drift_history = DriftHistory(config["chart_history_hours"] * 3600)
        self.data_logger = DataLogger(config["data_log_file"])

    def update_config(self, new_config):
        """Applies edited Settings: persists to disk and rebuilds the model
        objects. Only valid while stopped, since the mount/PHD2 connections
        aren't live."""
        if self.running:
            raise RuntimeError("Cannot change settings while running -- stop first.")

        self.config = new_config
        save_config(new_config)
        self._build_models(new_config)

        self.dry_run = new_config["dry_run"]
        self.current_offset = 0.0
        self.last_side_of_pier = None
        self.last_apply_time = 0.0
        self.session_start_time = None
        self._log("Settings updated and saved.")

    # -- logging -----------------------------------------------------------

    def _log(self, msg):
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
        self.log_queue.put(line)
        with open(self.config["log_file"], "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def drain_log_queue(self):
        """Called by the View on a timer to pull any pending log lines."""
        lines = []
        while True:
            try:
                lines.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        return lines

    def get_drift_snapshot(self):
        """Thread-safe (samples, rate_changes) snapshot for the View's drift chart."""
        return self.drift_history.snapshot()

    def clear_drift_history(self):
        """Removes the samples and markers currently shown on the drift chart."""
        self.drift_history.clear()
        self._log("Drift chart cleared.")

    # -- lifecycle -----------------------------------------------------------

    def start(self):
        if self.running:
            return
        self.mount.connect()
        self.last_side_of_pier = self.mount.get_side_of_pier()
        self.session_start_time = None  # re-anchored on the first guide step
        self.phd2.start()
        self.running = True
        self._log(f"Started (dry_run={self.dry_run}).")

    def stop(self):
        if not self.running:
            return
        self._log("Stopping -- resetting RightAscensionRate to 0.")
        self.phd2.stop()
        self.mount.disconnect()
        self.running = False

    def set_dry_run(self, value):
        self.dry_run = value
        self._log(f"Dry run set to {value}.")

    # -- PHD2 event handlers -------------------------------------------------

    def _on_guide_step(self, msg):
        ra_raw_px = msg.get("RADistanceRaw")
        if ra_raw_px is None:
            return
        ra_raw_arcsec = ra_raw_px * self.config["pixel_scale_arcsec"]
        # In simulation mode, msg carries the simulator's own clock (which
        # advances by a fixed step per tick regardless of real elapsed
        # time) so the trend fit stays in true arcsec/s units even when
        # sim_speed_multiplier makes ticks arrive faster than real time.
        now = msg.get("SimTimestamp", time.time())
        if self.session_start_time is None:
            self.session_start_time = now
        self.trend.add_sample(ra_raw_arcsec, now)
        self.drift_history.add_sample(now, ra_raw_arcsec)

        side = self.mount.get_side_of_pier()
        dec_deg = self.mount.get_declination()
        self.data_logger.log_guide_step(
            timestamp=datetime.fromtimestamp(now).isoformat(),
            elapsed_seconds=now - self.session_start_time,
            ra_raw_arcsec=ra_raw_arcsec,
            applied_ra_rate=self.current_offset,
            declination_deg=dec_deg,
            side_of_pier=side,
            dry_run=self.dry_run,
        )

        if self.last_side_of_pier is not None and side != self.last_side_of_pier:
            self._log(f"Pier side changed ({self.last_side_of_pier} -> {side}). "
                       f"Resetting trend window and rate offset.")
            self.trend.reset()
            self.current_offset = 0.0
            self.mount.set_ra_rate(0.0, self.dry_run)
            self.drift_history.add_rate_change(now, 0.0)
        self.last_side_of_pier = side

        if now - self.last_apply_time >= self.config["apply_interval_seconds"]:
            self.last_apply_time = now
            self._consider_adjustment(now)

    def _on_guiding_stopped(self):
        self._log("PHD2 guiding stopped -- resetting trend window (not the rate offset).")
        self.trend.reset()

    def _on_app_state(self, state):
        self._log(f"PHD2 AppState: {state}")

    # -- control logic -------------------------------------------------------

    def _consider_adjustment(self, now):
        slope, n = self.trend.fit_trend()
        if slope is None:
            self._log(f"Not enough samples yet for a trend fit "
                       f"({n}/{self.config['min_samples_for_trend']}).")
            return

        # slope is a real sky-angular rate (arcsec/s) from the guide camera,
        # unaffected by declination. But Telescope.RightAscensionRate is in
        # RA-TIME-seconds per sidereal second, not arcsec/s (RA is a time
        # coordinate) -- one RA-second is only 15.041" of real sky motion at
        # the celestial equator, and less elsewhere, scaled by cos(dec).
        # So converting an observed angular rate into the units the mount
        # actually expects needs cos(dec) as well as SIDEREAL_ARCSEC_PER_SEC.
        dec_deg = self.mount.get_declination()
        if dec_deg is None:
            self._log("WARNING: mount did not report Declination -- "
                       "assuming dec=0 for this cycle's rate conversion.")
            cos_dec = 1.0
        else:
            cos_dec = math.cos(math.radians(dec_deg))
            if abs(cos_dec) < MIN_COS_DEC:
                self._log(f"Declination {dec_deg:+.2f} deg is too close to the pole "
                           f"for a safe rate conversion -- skipping this cycle.")
                return

        # needed_offset is the RATE the raw RA error is CURRENTLY growing at
        # (converted to RightAscensionRate units) -- i.e. it's already the
        # residual left over after whatever offset is presently applied
        # (setting RightAscensionRate genuinely changes what the guider
        # sees). So it's an INCREMENT still needed on top of current_offset,
        # not an absolute target to move current_offset toward -- we ADD a
        # damped fraction of it (integral-style), rather than steering
        # current_offset toward it as a set-point.
        previous_offset = self.current_offset
        needed_offset = slope / (SIDEREAL_ARCSEC_PER_SEC * cos_dec)
        delta = needed_offset * self.config["damping_factor"]
        max_step = self.config["max_step_per_cycle"]
        delta = max(-max_step, min(max_step, delta))
        new_offset = previous_offset + delta

        self._log(f"Trend fit: {slope:+.5f} arcsec/s over {n} samples (dec={dec_deg}, cos={cos_dec:.4f}) -> "
                   f"residual {needed_offset:+.5f}, current {previous_offset:+.5f}, "
                   f"applying delta {delta:+.5f} -> new {new_offset:+.5f}")

        if self.session_start_time is None:
            self.session_start_time = now
        self.data_logger.log_adjustment(
            timestamp=datetime.fromtimestamp(now).isoformat(),
            elapsed_seconds=now - self.session_start_time,
            previous_ra_rate=previous_offset,
            slope_arcsec_per_sec=slope,
            n_samples=n,
            declination_deg=dec_deg,
            cos_dec=cos_dec,
            needed_offset_increment=needed_offset,
            damping_factor=self.config["damping_factor"],
            delta_applied=delta,
            new_ra_rate=new_offset,
            dry_run=self.dry_run,
        )

        self.current_offset = new_offset
        self.mount.set_ra_rate(new_offset, self.dry_run)
        self.drift_history.add_rate_change(now, new_offset)
