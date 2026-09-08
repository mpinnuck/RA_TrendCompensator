"""ViewModel: owns the model objects, exposes thread-safe log/state to the View."""

import math
import queue
import threading
import time
from datetime import datetime

from src.config import resolve_log_path, save_config
from src.model.constants import SIDEREAL_ARCSEC_PER_SEC, format_pier_side
from src.model.data_logger import DataLogger
from src.model.guide_quality_monitor import GuideQualityMonitor
from src.model.mount_controller import MountController
from src.model.phd2_client import PHD2Client
from src.model.simulated_mount import SimulatedMountController
from src.model.simulated_phd2_source import SimulatedPHD2Source
from src.model.status_server import StatusServer
from src.model.trend_estimator import TrendEstimator
from src.model.drift_history import DriftHistory

# Below this, cos(dec) is small enough that a tiny slope estimate translates
# into a huge RightAscensionRate value -- treat it as "declination unknown /
# unsafe to correct" and skip the adjustment rather than blow up. This is
# ~89.4 degrees -- no real imaging target sits this close to the pole.
MIN_COS_DEC = 0.01

# How often the background maintenance loop wakes up to poll mount tracking
# state and pier side, and to consider re-sending the current offset. This
# is independent of maintain_interval_seconds (the throttle on how often a
# re-send actually happens) and of apply_interval_seconds (how often a NEW
# trend-based adjustment is computed) -- this is just the poll granularity.
MAINTAIN_POLL_SECONDS = 2.0


class RATrendCompensatorViewModel:
    def __init__(self, config):
        self.config = config
        self.log_queue = queue.Queue()
        self.running = False
        self.dry_run = config["dry_run"]
        self.current_offset = 0.0
        self.last_side_of_pier = None
        self.last_apply_time = 0.0
        self.last_maintain_time = 0.0
        self.session_start_time = None
        self.last_slope = None
        self.last_trend_n_samples = 0
        self.last_raw_arcsec = None
        self.last_phd2_avg_dist_arcsec = None

        # Three-state model (see _is_actively_correcting()/_is_idle() docs
        # below): phd2_guiding and paused track PHD2's own signals;
        # mount_tracking tracks the mount's hardware state directly, polled
        # by the maintenance thread since PHD2 has no idea whether the
        # mount is tracking at all.
        self.phd2_guiding = False
        self.paused = False
        self.mount_tracking = None

        self._maintain_thread = None
        self._maintain_stop = None
        self._state_lock = threading.RLock()

        self._build_models(config)

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
                config["max_rate_magnitude"], self._log,
                declination_deg=config["sim_declination_deg"],
                right_ascension_hours=config["sim_target_ra_hours"],
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
            self._log("Simulation mode active -- using synthetic PHD2/mount data. "
                       "Note: the simulator does not emit Settling/Paused events, "
                       "so pause behavior isn't exercised in simulation mode.")
        else:
            self.mount = MountController(
                config["ascom_prog_id"], config["max_rate_magnitude"], self._log
            )
            self.phd2 = PHD2Client(
                config["phd2_host"], config["phd2_port"],
                on_guide_step=self._on_guide_step,
                on_guiding_stopped=self._on_guiding_stopped,
                on_app_state=self._on_app_state,
                on_settling=self._on_settling,
                on_settle_done=self._on_settle_done,
                on_paused=self._on_paused,
                on_resumed=self._on_resumed,
                logger=self._log,
            )

        self.trend = TrendEstimator(config["window_seconds"], config["min_samples_for_trend"])
        self.guide_quality = GuideQualityMonitor(
            config["rms_window_seconds"], config["rms_trend_window_seconds"],
            config["rms_sample_interval_seconds"],
        )
        self.drift_history = DriftHistory(config["chart_history_hours"] * 3600)
        self.data_logger = DataLogger(resolve_log_path(config, "data_log_file"))

        # The status server's lifecycle is independent of guiding start/stop
        # (an external tool like a NINA plugin should see "app running, not
        # yet guiding" rather than no connection at all) -- so unlike mount/
        # phd2, it must be explicitly stopped here before rebuilding, since
        # update_config() calls this again while nothing else has torn it
        # down (the app is stopped, but stopped != status server torn down).
        if getattr(self, "status_server", None) is not None:
            self.status_server.stop()
        if config.get("status_server_enabled", True):
            self.status_server = StatusServer(
                config["status_server_host"], config["status_server_port"],
                get_snapshot=self.get_status_snapshot,
                interval_seconds=config["status_server_interval_seconds"],
                logger=self._log,
            )
            self.status_server.start()
        else:
            self.status_server = None

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
        with open(resolve_log_path(self.config, "log_file"), "a", encoding="utf-8") as f:
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

    def get_status_client_count(self):
        """Return the number of clients connected to the status server."""
        return self.status_server.client_count() if self.status_server is not None else 0

    def get_mount_coordinates(self):
        """Return the mount's live Right Ascension (hours) and Declination (degrees)."""
        return self.mount.get_right_ascension(), self.mount.get_declination()

    def clear_drift_history(self):
        """Removes the samples and markers currently shown on the drift chart."""
        self.drift_history.clear()
        self._log("Drift chart cleared.")

    def get_status_snapshot(self):
        """JSON-serializable status snapshot broadcast by the status server
        -- e.g. for a NINA plugin to display live compensator state."""
        with self._state_lock:
            rms_trend_slope, rms_trend_n = self.guide_quality.get_rms_trend()
            return {
                "running": self.running,
                "phd2_connected": self.phd2.is_connected,
                "phd2_guiding": self.phd2_guiding,
                "paused": self.paused,
                "mount_tracking": self.mount_tracking,
                "actively_correcting": self._is_actively_correcting(),
                "dry_run": self.dry_run,
                "current_offset": self.current_offset,
                "current_ra_deviation_arcsec": self.last_raw_arcsec,
                "last_slope_arcsec_per_sec": self.last_slope,
                "last_trend_n_samples": self.last_trend_n_samples,
                "guide_rms_arcsec": self.guide_quality.current_rms,
                "guide_rms_trend_arcsec_per_sec": rms_trend_slope,
                "guide_rms_trend_n_samples": rms_trend_n,
                "phd2_avg_dist_arcsec": self.last_phd2_avg_dist_arcsec,
                "right_ascension_hours": self.mount.get_right_ascension(),
                "declination_deg": self.mount.get_declination(),
                "side_of_pier": format_pier_side(self.last_side_of_pier),
                "timestamp": time.time(),
            }

    # -- lifecycle -----------------------------------------------------------

    def start(self):
        if self.running:
            return
        self.mount.connect()
        self.last_side_of_pier = self.mount.get_side_of_pier()
        self.mount_tracking = self.mount.get_tracking()
        self.session_start_time = None  # re-anchored on the first guide step
        self.phd2.start()
        self.running = True
        self._start_maintain_loop()
        self._log(f"Started (dry_run={self.dry_run}).")

    def stop(self):
        if not self.running:
            return
        self._log("Stopping -- resetting RightAscensionRate to 0.")
        self._stop_maintain_loop()
        self.phd2.stop()
        self.mount.disconnect()
        self.running = False
        self.phd2_guiding = False
        self.paused = False

    def shutdown(self):
        """Called when the whole app is closing (not just Stop) -- tears
        down background resources that live independently of the guiding
        start/stop cycle, like the status server."""
        if self.running:
            self.stop()
        if self.status_server is not None:
            self.status_server.stop()

    def set_dry_run(self, value):
        self.dry_run = value
        self._log(f"Dry run set to {value}.")

    # -- three-state model -----------------------------------------------------

    def _is_actively_correcting(self):
        """Tracking + PHD2 actively guiding (not paused) -- the only state
        where NEW trend samples are accumulated and NEW adjustments are
        computed. mount_tracking is treated as "ok" when None (driver
        doesn't report it) to preserve prior behavior on such drivers --
        only an explicit False blocks this."""
        return self.mount_tracking is not False and self.phd2_guiding and not self.paused

    def _is_maintain_state(self):
        """Tracking, but not actively correcting (paused for dither/focus/
        flip, or PHD2 isn't guiding at all) -- no new computation, but the
        last known-good offset is worth periodically re-asserting in case
        something else (an autofocus routine, a flip handler, the driver
        itself) silently reset RightAscensionRate while we weren't
        watching for it via guide steps."""
        return self.mount_tracking is not False and not self._is_actively_correcting()

    def _start_maintain_loop(self):
        self._maintain_stop = threading.Event()
        self._maintain_thread = threading.Thread(target=self._maintain_loop, daemon=True)
        self._maintain_thread.start()

    def _stop_maintain_loop(self):
        if self._maintain_stop is not None:
            self._maintain_stop.set()
        if self._maintain_thread is not None:
            self._maintain_thread.join(timeout=2)
        self._maintain_thread = None
        self._maintain_stop = None

    def _maintain_loop(self):
        """Runs the whole time the app is Started, independent of whether
        guide steps are arriving -- this is the only way to notice a pier
        flip or a tracking-state change during a pause (autofocus, dither,
        pre-guide-resume after a flip), when no GuideStep events are
        coming in at all."""
        while not self._maintain_stop.is_set():
            try:
                self._maintain_tick()
            except Exception as e:
                self._log(f"WARNING: maintenance tick failed: {e}")
            self._maintain_stop.wait(MAINTAIN_POLL_SECONDS)

    def _maintain_tick(self):
        now = time.time()

        tracking = self.mount.get_tracking()
        if tracking != self.mount_tracking:
            self._log(f"Mount tracking changed: {self.mount_tracking} -> {tracking}.")
        self.mount_tracking = tracking

        side = self.mount.get_side_of_pier()

        with self._state_lock:
            if self.last_side_of_pier is not None and side != self.last_side_of_pier:
                self._log(f"Pier side changed ({format_pier_side(self.last_side_of_pier)} -> {format_pier_side(side)}). "
                           f"Resetting trend window and rate offset.")
                self.trend.reset()
                self.guide_quality.reset()
                self.current_offset = 0.0
                self.mount.set_ra_rate(0.0, self.dry_run)
                self.drift_history.add_rate_change(now, 0.0)
            self.last_side_of_pier = side

            if self._is_maintain_state() and now - self.last_maintain_time >= self.config["maintain_interval_seconds"]:
                self.last_maintain_time = now
                self.mount.set_ra_rate(self.current_offset, self.dry_run)

    # -- PHD2 event handlers -------------------------------------------------

    def _on_guide_step(self, msg):
        ra_raw_px = msg.get("RADistanceRaw")
        if ra_raw_px is None:
            return
        ra_raw_arcsec = ra_raw_px * self.config["pixel_scale_arcsec"]

        with self._state_lock:
            self.last_raw_arcsec = ra_raw_arcsec

            # AvgDist is PHD2's own smoothed distance (combines RA+Dec, not
            # RA-isolated), sent with every real GuideStep event -- absent from
            # our own simulated messages, so this stays None in simulation mode.
            # It's a cross-check against our own RA-only RMS, computed a
            # different way by PHD2 itself, not a replacement for it.
            avg_dist_px = msg.get("AvgDist")
            self.last_phd2_avg_dist_arcsec = (
                avg_dist_px * self.config["pixel_scale_arcsec"] if avg_dist_px is not None else None
            )

            # In simulation mode, msg carries the simulator's own clock (which
            # advances by a fixed step per tick regardless of real elapsed
            # time) so the trend fit stays in true arcsec/s units even when
            # sim_speed_multiplier makes ticks arrive faster than real time.
            now = msg.get("SimTimestamp", time.time())
            if self.session_start_time is None:
                self.session_start_time = now

            # Pier-side change detection and reset now live in _maintain_tick()
            # (runs regardless of whether guide steps are arriving), so a flip
            # during a pause is caught immediately rather than waiting for
            # guiding to resume.

            if not self._is_actively_correcting():
                # Still worth logging the raw deviation/CSV row for reference,
                # but no new trend sample or adjustment while paused/idle --
                # see _is_actively_correcting()'s docstring.
                self.data_logger.log_guide_step(
                    timestamp=datetime.fromtimestamp(now).isoformat(),
                    elapsed_seconds=now - self.session_start_time,
                    ra_raw_arcsec=ra_raw_arcsec,
                    applied_ra_rate=self.current_offset,
                    declination_deg=self.mount.get_declination(),
                    side_of_pier=self.last_side_of_pier,
                    dry_run=self.dry_run,
                    phd2_avg_dist_arcsec=self.last_phd2_avg_dist_arcsec,
                )
                return

            self.trend.add_sample(ra_raw_arcsec, now)
            self.guide_quality.add_sample(now, ra_raw_arcsec)
            self.drift_history.add_sample(now, ra_raw_arcsec)

            dec_deg = self.mount.get_declination()
            self.data_logger.log_guide_step(
                timestamp=datetime.fromtimestamp(now).isoformat(),
                elapsed_seconds=now - self.session_start_time,
                ra_raw_arcsec=ra_raw_arcsec,
                applied_ra_rate=self.current_offset,
                declination_deg=dec_deg,
                side_of_pier=self.last_side_of_pier,
                dry_run=self.dry_run,
                phd2_avg_dist_arcsec=self.last_phd2_avg_dist_arcsec,
            )

            if now - self.last_apply_time >= self.config["apply_interval_seconds"]:
                self.last_apply_time = now
                self._consider_adjustment(now)

    def _on_guiding_stopped(self):
        with self._state_lock:
            if self.phd2_guiding:
                self._log("PHD2 guiding stopped -- resetting trend window (rate offset retained).")
            self.phd2_guiding = False
            self.trend.reset()
            self.guide_quality.reset()

    def _on_app_state(self, state):
        self._log(f"PHD2 AppState: {state}")
        if state == "Guiding" and not self.phd2_guiding:
            self.phd2_guiding = True
            self.session_start_time = None  # re-anchored on the first guide step of this session
            self._log("Guiding started -- compensation active.")

    def _on_settling(self):
        """Dither settling -- the guide star is intentionally offset right
        now, so this pauses sample accumulation WITHOUT resetting the
        trend window (unlike _on_guiding_stopped): the underlying drift
        trend is still valid, only the guide signal is briefly disturbed."""
        if not self.paused:
            self._log("Pausing compensation: dither settling.")
        self.paused = True

    def _on_settle_done(self):
        if self.paused:
            self._log("Resuming compensation: settle complete.")
        self.paused = False

    def _on_paused(self):
        """PHD2's explicit pause -- how NINA typically suspends guiding
        around a focus routine or a meridian flip. Same non-resetting
        pause behavior as _on_settling."""
        if not self.paused:
            self._log("Pausing compensation: PHD2 paused (focus/flip).")
        self.paused = True

    def _on_resumed(self):
        if self.paused:
            self._log("Resuming compensation: PHD2 resumed.")
        self.paused = False

    # -- control logic -------------------------------------------------------


    def _consider_adjustment(self, now):
        with self._state_lock:
            slope, n = self.trend.fit_trend()
            if slope is None:
                self._log(f"Not enough samples yet for a trend fit "
                           f"({n}/{self.config['min_samples_for_trend']}).")
                return

            self.last_slope = slope
            self.last_trend_n_samples = n

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
