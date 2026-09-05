"""Real, log-derived drift-rate profiles for simulation mode.

Each profile is a list of (elapsed_seconds, drift_rate_arcsec_per_sec)
points, piecewise-linearly interpolated by SimulatedPHD2Source when passed
as its drift_profile. These aren't invented numbers -- they're derived from
an actual PHD2 guide log analysis (see the "PHD2 guiding settings for
Celestron 9.25 EdgeHD" conversation), so replaying one reproduces the
*shape* of a real session's RA bias rather than an idealized constant or
linear ramp.
"""

# NGC 6744, 2026-09-03 session (C9.25 EdgeHD, AM5N, ASI174MM mini via OAG,
# 0.51"/px image scale). Derived from the guide log's RADistanceRaw values,
# binned into ~13-minute (700-frame) chunks; each point here is the net
# signed sum for that bin converted to an average rate:
#   rate = bin_sum_px * pixel_scale_arcsec / bin_duration_seconds
# using bin_duration = 13 * 60 = 780s (the bins' actual spacing).
#
# Shape: flat/mixed for the first ~50 minutes (before the meridian flip),
# then a sustained climb starting right at the flip and continuing for
# most of the rest of the session -- this is the real behavior that
# motivated adding the drift-ramp feature and finding/fixing the control
# law's constant-drift undercorrection bug.
NGC6744_2026_09_03 = [
    (0, 0.0626),
    (780, 0.0093),
    (1560, 0.0333),
    (2340, -0.0402),
    (3120, -0.0041),
    (3900, 0.0732),
    (4680, 0.0902),
    (5460, 0.1454),
    (6240, 0.1325),
    (7020, 0.1882),
    (7800, 0.2251),
    (8580, 0.1966),
    (9360, 0.2118),
    (10140, 0.2516),
    (10920, 0.2534),
    (11700, 0.2496),
    (12480, 0.1470),
]

PROFILES = {
    "NGC6744_2026_09_03": NGC6744_2026_09_03,
}

# Target metadata the profile's numbers were actually recorded at -- loading
# a profile via Settings also sets these fields to match, since the cos(dec)
# rate-conversion fix and the hour-angle-driven polar-alignment model mean
# declination and starting hour angle both materially affect the replay,
# even though the drift_profile points themselves are just angular arcsec/s.
#
# start_hour_angle_hours is approximate: the meridian flip fell at frame
# ~2551 of ~11595 over a ~3.5h session, i.e. ~47 minutes in, matching "the
# first 50 minutes was before the meridian flip" -- so the session started
# at roughly HA = -47/60 ~= -0.78h (47 minutes before transit).
PROFILE_TARGETS = {
    "NGC6744_2026_09_03": {
        "name": "NGC 6744",
        "ra_hours": 19.1628,
        "dec_deg": -63.8,
        "start_hour_angle_hours": -0.78,
    },
}
