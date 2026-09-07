"""Lightweight stand-ins for the hardware/network-facing model classes, so
tests can drive the ViewModel without a real mount connected or a running
PHD2 instance."""


class FakeMountController:
    """Drop-in replacement for MountController -- no ASCOM driver required."""

    def __init__(self, prog_id=None, max_rate_magnitude=1.0, logger=None, declination_deg=0.0):
        self.prog_id = prog_id
        self.max_rate_magnitude = max_rate_magnitude
        self.logger = logger or (lambda msg: None)
        self.connected = False
        self.ra_rate = 0.0
        self.side_of_pier = 0
        self.right_ascension_hours = 0.0
        self.declination_deg = declination_deg
        self.set_ra_rate_calls = []

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.set_ra_rate(0.0, dry_run=False, force=True)
        self.connected = False

    def get_ra_rate(self):
        return self.ra_rate

    def get_side_of_pier(self):
        return self.side_of_pier

    def get_right_ascension(self):
        return self.right_ascension_hours

    def get_declination(self):
        return self.declination_deg

    def set_ra_rate(self, value, dry_run, force=False):
        value = max(-self.max_rate_magnitude, min(self.max_rate_magnitude, value))
        self.set_ra_rate_calls.append(value)
        if not dry_run or force:
            self.ra_rate = value


class FakePHD2Client:
    """Drop-in replacement for PHD2Client -- no real socket connection."""

    def __init__(self, host=None, port=None, on_guide_step=None,
                 on_guiding_stopped=None, on_app_state=None, logger=None):
        self.on_guide_step = on_guide_step
        self.on_guiding_stopped = on_guiding_stopped
        self.on_app_state = on_app_state
        self.logger = logger or (lambda msg: None)
        self.started = False
        self.is_connected = False

    def start(self):
        self.started = True
        self.is_connected = True

    def stop(self):
        self.started = False
        self.is_connected = False

    def emit_guide_step(self, ra_distance_raw):
        """Test helper: simulate PHD2 sending a GuideStep event."""
        self.on_guide_step({"RADistanceRaw": ra_distance_raw})
