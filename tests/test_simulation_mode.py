"""End-to-end simulation-mode tests. Unlike test_view_model.py, these use
the REAL SimulatedMountController and SimulatedPHD2Source (via
simulation_mode: True in config) -- no fakes, no mocking. vm.phd2.tick() is
called directly and synchronously (bypassing the background thread) so the
test is fully deterministic and needs no sleeps.

_consider_adjustment()'s control law was previously double-counting
current_offset (treating the already-residual needed_offset as an absolute
target rather than an increment), which meant a sustained constant drift
only ever got HALF corrected, permanently, regardless of damping_factor.
That's been fixed (delta = needed_offset * damping_factor). With
drift_walk_std=0 and noise_arcsec=0, the closed loop here is deterministic,
so these tests check the corrected convergence directly:
  - a constant true drift converges to fully correcting it (fraction -> 1.0)
  - a linearly ramping true drift (simulating drift that gets worse over a
    session) settles to a small, BOUNDED tracking lag rather than falling
    permanently further behind

IMPORTANT: apply_interval_seconds must not be too small relative to
window_seconds, or the loop reacts before the trend window has had time to
reflect the previous correction's effect, which can cause oscillation
rather than convergence -- this isn't specific to the fix, it's a general
control-loop stability concern. The defaults (120s / 300s) are safely
within the well-behaved regime; these tests use scaled-down but similarly-
proportioned values for fast execution.
"""

from src.viewmodel.view_model import RATrendCompensatorViewModel, SIDEREAL_ARCSEC_PER_SEC

import pytest


def _sim_config(tmp_path, **overrides):
    config = {
        "phd2_host": "localhost",
        "phd2_port": 4400,
        "ascom_prog_id": "SIM",
        "dry_run": False,
        "window_seconds": 60,
        "min_samples_for_trend": 10,
        "apply_interval_seconds": 20,
        "damping_factor": 0.3,
        "max_rate_magnitude": 1.0,
        "max_step_per_cycle": 1.0,
        "pixel_scale_arcsec": 0.5,
        "log_file": str(tmp_path / "sim_test.log"),
        "data_log_file": str(tmp_path / "sim_test_data.csv"),
        "chart_history_hours": 8,
        "simulation_mode": True,
        "sim_true_drift_arcsec_per_sec": 0.05,
        "sim_drift_walk_std": 0.0,
        "sim_drift_ramp_arcsec_per_sec_per_hour": 0.0,
        "sim_noise_arcsec": 0.0,
        "sim_pull_to_zero_per_step": 0.0,
        "sim_guide_step_interval_s": 2.0,
        "sim_speed_multiplier": 1.0,
        "sim_declination_deg": 0.0,
        "sim_target_name": "",
        "sim_target_ra_hours": 0.0,
        "sim_start_hour_angle_hours": 0.0,
        "sim_polar_error_arcmin": 0.0,
        "sim_polar_error_angle_deg": 0.0,
        "sim_bias_direction": "west",
        "status_server_enabled": False,
        "rms_window_seconds": 60,
        "rms_trend_window_seconds": 300,
        "rms_sample_interval_seconds": 5,
    }
    config.update(overrides)
    return config


def _start_without_thread(vm):
    """Connects the (simulated) mount and marks the ViewModel as running,
    without starting SimulatedPHD2Source's background thread -- so the test
    can call vm.phd2.tick() directly for deterministic, sleep-free control."""
    vm.mount.connect()
    vm.last_side_of_pier = vm.mount.get_side_of_pier()
    vm.running = True


def test_simulation_mode_builds_real_model_objects_with_no_mocking(tmp_path):
    from src.model.simulated_mount import SimulatedMountController
    from src.model.simulated_phd2_source import SimulatedPHD2Source

    vm = RATrendCompensatorViewModel(_sim_config(tmp_path))
    assert isinstance(vm.mount, SimulatedMountController)
    assert isinstance(vm.phd2, SimulatedPHD2Source)
    assert vm.get_status_snapshot()["phd2_connected"] is False


def test_guide_steps_populate_chart_history_via_real_tick(tmp_path):
    vm = RATrendCompensatorViewModel(_sim_config(tmp_path))
    _start_without_thread(vm)

    for _ in range(50):
        vm.phd2.tick()

    samples, rate_changes = vm.get_drift_snapshot()
    assert len(samples) == 50
    assert len(rate_changes) >= 1


def test_closed_loop_offset_responds_to_the_applied_rate(tmp_path):
    # If the loop is genuinely closed, the offset the compensator applies
    # must itself feed back into the next guide step's residual -- i.e.
    # get_applied_rate() inside the simulator should reflect what the
    # ViewModel actually set on the mount.
    vm = RATrendCompensatorViewModel(_sim_config(tmp_path))
    _start_without_thread(vm)

    for _ in range(300):
        vm.phd2.tick()

    assert vm.current_offset != 0.0
    assert vm.mount.get_ra_rate() == vm.current_offset


def test_constant_drift_converges_to_full_correction(tmp_path):
    """A sustained, constant true drift rate should be fully corrected
    (fraction -> 1.0), not the pre-fix steady state of 0.5."""
    true_drift = 0.05
    vm = RATrendCompensatorViewModel(_sim_config(tmp_path, sim_true_drift_arcsec_per_sec=true_drift))
    _start_without_thread(vm)

    for _ in range(600):
        vm.phd2.tick()

    full_correction_target = true_drift / SIDEREAL_ARCSEC_PER_SEC
    assert vm.current_offset == pytest.approx(full_correction_target, rel=0.01)


def test_compensator_corrects_east_and_west_bias_symmetrically(tmp_path):
    """The algorithm shouldn't care which physical direction the drift is
    in -- it should converge to the same MAGNITUDE of correction (opposite
    sign) whether the configured bias is west or east."""
    true_drift = 0.05

    vm_west = RATrendCompensatorViewModel(
        _sim_config(tmp_path, sim_true_drift_arcsec_per_sec=true_drift, sim_bias_direction="west")
    )
    _start_without_thread(vm_west)
    for _ in range(600):
        vm_west.phd2.tick()

    vm_east = RATrendCompensatorViewModel(
        _sim_config(tmp_path, sim_true_drift_arcsec_per_sec=true_drift, sim_bias_direction="east")
    )
    _start_without_thread(vm_east)
    for _ in range(600):
        vm_east.phd2.tick()

    assert vm_west.current_offset == pytest.approx(-vm_east.current_offset, rel=0.01)


def test_convergence_is_full_regardless_of_damping_factor(tmp_path):
    true_drift = 0.05
    full_correction_target = true_drift / SIDEREAL_ARCSEC_PER_SEC

    for damping_factor in (0.1, 0.3, 0.7):
        vm = RATrendCompensatorViewModel(
            _sim_config(tmp_path, sim_true_drift_arcsec_per_sec=true_drift, damping_factor=damping_factor)
        )
        _start_without_thread(vm)
        for _ in range(1500):
            vm.phd2.tick()

        fraction = vm.current_offset / full_correction_target
        assert fraction == pytest.approx(1.0, rel=0.02), f"damping_factor={damping_factor}"


def test_ramping_drift_settles_to_a_bounded_tracking_lag(tmp_path):
    """Reproduces a drift that gets steadily worse over a session (e.g. a
    fixed polar-alignment error against a target's changing hour angle).
    The corrected control law can't perfectly track a moving target (it has
    no true integral term), but the lag should stabilize to a small,
    constant value rather than growing without bound as the session
    continues -- that's the key improvement over the pre-fix behavior."""
    vm = RATrendCompensatorViewModel(_sim_config(
        tmp_path,
        sim_true_drift_arcsec_per_sec=0.0,
        sim_drift_ramp_arcsec_per_sec_per_hour=0.5,
    ))
    _start_without_thread(vm)

    lags = []
    checkpoints = {1600, 2400, 3200, 4000}
    for i in range(1, max(checkpoints) + 1):
        vm.phd2.tick()
        if i in checkpoints:
            target_now = vm.phd2._true_drift_rate / SIDEREAL_ARCSEC_PER_SEC
            lags.append(target_now - vm.current_offset)

    # The true drift (and hence target offset) is still climbing throughout
    # this whole run, but the lag itself should have settled to a roughly
    # constant value by the later checkpoints -- not kept growing alongside it.
    assert lags[-1] == pytest.approx(lags[-2], rel=0.05)
    assert lags[-1] == pytest.approx(lags[0], rel=0.1)


def test_real_ngc6744_session_profile_is_substantially_corrected(tmp_path):
    """Replays the ACTUAL NGC 6744 session's derived drift-rate shape
    (see real_session_profiles.py) through the fixed compensator, using
    realistic (non-scaled-down) window/apply-interval settings. Confirms
    the compensator's applied offset tracks the real observed bias closely
    enough that the residual (uncompensated) rate stays much smaller than
    the true drift itself would be with no compensation at all -- i.e.
    this isn't just a synthetic-scenario improvement, it holds on Mark's
    own recorded session shape."""
    from src.model.real_session_profiles import NGC6744_2026_09_03
    import math

    declination_deg = -63.8
    cos_dec = math.cos(math.radians(declination_deg))

    vm = RATrendCompensatorViewModel(_sim_config(
        tmp_path,
        window_seconds=300,
        min_samples_for_trend=60,
        apply_interval_seconds=120,
        damping_factor=0.3,
        max_step_per_cycle=0.05,
        pixel_scale_arcsec=0.51,
        sim_true_drift_arcsec_per_sec=0.0,
        sim_drift_profile=NGC6744_2026_09_03,
        sim_guide_step_interval_s=2.0,
        sim_declination_deg=declination_deg,
    ))
    _start_without_thread(vm)

    # Run through and a bit beyond the real session's ~12480s duration.
    total_ticks = int(13000 / 2.0)
    true_drifts = []
    residuals = []
    # Only evaluate from the point the trend has had a chance to settle
    # onto the post-meridian-flip climb (skip the first ~4000s).
    settle_ticks = int(4000 / 2.0)
    for i in range(1, total_ticks + 1):
        vm.phd2.tick()
        if i > settle_ticks:
            true_drift = vm.phd2._true_drift_rate
            # Must match the simulator's own conversion (which includes
            # cos(dec)) to be a meaningful comparison -- see
            # SimulatedPHD2Source.tick().
            residual = true_drift - vm.current_offset * SIDEREAL_ARCSEC_PER_SEC * cos_dec
            true_drifts.append(true_drift)
            residuals.append(residual)

    mean_abs_true_drift = sum(abs(v) for v in true_drifts) / len(true_drifts)
    mean_abs_residual = sum(abs(v) for v in residuals) / len(residuals)

    # With no compensation at all, the residual would just equal the true
    # drift. The compensator should cut the average uncompensated residual
    # to well under half of that.
    assert mean_abs_residual < mean_abs_true_drift * 0.5


def test_nonzero_declination_converges_to_a_larger_offset_for_the_same_drift(tmp_path):
    """The cos(dec) fix: correcting the same angular drift rate away from
    the celestial equator requires a LARGER RightAscensionRate offset, by
    a factor of 1/cos(dec) -- since RightAscensionRate is in RA-time-
    seconds per sidereal second, not arcsec/s, and one RA-second is only
    15.041" of real sky motion at dec=0, less elsewhere."""
    import math

    true_drift = 0.05
    declination_deg = -63.8
    cos_dec = math.cos(math.radians(declination_deg))

    vm_equator = RATrendCompensatorViewModel(_sim_config(
        tmp_path, sim_true_drift_arcsec_per_sec=true_drift, sim_declination_deg=0.0
    ))
    _start_without_thread(vm_equator)
    for _ in range(600):
        vm_equator.phd2.tick()

    vm_south = RATrendCompensatorViewModel(_sim_config(
        tmp_path, sim_true_drift_arcsec_per_sec=true_drift, sim_declination_deg=declination_deg
    ))
    _start_without_thread(vm_south)
    for _ in range(600):
        vm_south.phd2.tick()

    # Both should fully correct the SAME angular drift (physical residual
    # -> 0), but the offset needed to do so at dec=-63.8 should be about
    # 1/cos(dec) times larger than at the equator.
    ratio = vm_south.current_offset / vm_equator.current_offset
    assert ratio == pytest.approx(1 / cos_dec, rel=0.02)


def test_missing_declination_falls_back_to_equator_assumption(tmp_path):
    """If the mount can't report Declination (e.g. driver quirk), the
    compensator should still function -- just as if dec=0 -- rather than
    crashing or refusing to adjust."""
    vm = RATrendCompensatorViewModel(_sim_config(tmp_path))
    _start_without_thread(vm)
    vm.mount.get_declination = lambda: None  # simulate a driver that can't report it

    for _ in range(300):
        vm.phd2.tick()

    assert vm.current_offset != 0.0  # still adjusting, not stuck/crashed


def test_declination_near_the_pole_skips_adjustment_safely(tmp_path):
    """Very close to +/-90 deg, cos(dec) is near zero and a tiny slope
    would imply a huge RightAscensionRate -- the compensator should skip
    the adjustment that cycle rather than compute a nonsensical value."""
    vm = RATrendCompensatorViewModel(_sim_config(tmp_path, sim_declination_deg=-89.9))
    _start_without_thread(vm)

    for _ in range(300):
        vm.phd2.tick()

    assert vm.current_offset == 0.0  # never adjusted -- stayed at the safe default
