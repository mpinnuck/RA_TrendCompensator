"""In-memory stand-in for MountController -- same public interface, no ASCOM
driver required. Used by simulation mode so the app's control logic can be
exercised (and its effect on drift observed) without a telescope connected.
"""


class SimulatedMountController:
    def __init__(self, max_rate_magnitude, logger, declination_deg=0.0, right_ascension_hours=0.0):
        self.max_rate_magnitude = max_rate_magnitude
        self.logger = logger
        self.connected = False
        self._ra_rate = 0.0
        self._side_of_pier = 0
        self._declination_deg = declination_deg
        self._right_ascension_hours = right_ascension_hours

    def connect(self):
        self.connected = True
        self.logger("[SIM] Virtual mount connected.")

    def disconnect(self):
        try:
            self.set_ra_rate(0.0, dry_run=False, force=True)
        except Exception as e:
            self.logger(f"[SIM] WARNING: could not reset RightAscensionRate to 0 on exit: {e}")
        self.connected = False
        self.logger("[SIM] Virtual mount disconnected.")

    def get_ra_rate(self):
        return self._ra_rate

    def get_side_of_pier(self):
        return self._side_of_pier

    def get_right_ascension(self):
        return self._right_ascension_hours

    def get_declination(self):
        return self._declination_deg

    def set_declination(self, declination_deg):
        """Test/simulation helper -- a real mount's Declination is read-only
        from this app's perspective; a simulated one needs to be told what
        target it's supposedly pointed at."""
        self._declination_deg = declination_deg

    def set_ra_rate(self, value, dry_run, force=False):
        value = max(-self.max_rate_magnitude, min(self.max_rate_magnitude, value))
        if dry_run and not force:
            self.logger(f"[DRY RUN][SIM] Would set RightAscensionRate = {value:.4f}")
            return
        self._ra_rate = value
        self.logger(f"[SIM] Set RightAscensionRate = {value:.4f}")
