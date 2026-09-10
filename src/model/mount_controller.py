"""Wraps the ASCOM telescope COM driver for reading/setting RightAscensionRate."""

import threading

import pythoncom
import win32com.client


class MountController:
    def __init__(self, prog_id, max_rate_magnitude, logger):
        self.prog_id = prog_id
        self.max_rate_magnitude = max_rate_magnitude
        self.logger = logger
        self.connected = False
        self._git = None
        self._git_cookie = None
        # A raw win32com dispatch pointer is apartment-threaded -- reusing the
        # one created by connect() (on the GUI thread) directly from the
        # maintenance loop and PHD2's guide-step thread caused intermittent,
        # silently-swallowed COM failures (e.g. "Property ... can not be
        # set", or a property read throwing and getting treated as None).
        # Each thread instead gets its own proxy, fetched from the Global
        # Interface Table and cached here.
        self._local = threading.local()

    def connect(self):
        pythoncom.CoInitialize()
        telescope = win32com.client.Dispatch(self.prog_id)
        telescope.Connected = True
        if not telescope.Connected:
            raise RuntimeError("Mount driver reported Connected = False")
        self._git = pythoncom.CoCreateInstance(
            pythoncom.CLSID_StdGlobalInterfaceTable, None,
            pythoncom.CLSCTX_INPROC_SERVER, pythoncom.IID_IGlobalInterfaceTable,
        )
        self._git_cookie = self._git.RegisterInterfaceInGlobal(telescope._oleobj_, pythoncom.IID_IDispatch)
        self.telescope = telescope
        self.connected = True
        self.logger(f"Connected to {self.prog_id}")

    @property
    def telescope(self):
        """Per-thread COM proxy. The setter caches an explicit value for the
        calling thread only (used by connect() and by tests); otherwise this
        marshals a fresh proxy from the Global Interface Table for whichever
        thread is asking, since a proxy created elsewhere can't safely cross
        threads on its own."""
        cached = getattr(self._local, "telescope", None)
        if cached is not None:
            return cached
        if self._git is None:
            return None
        pythoncom.CoInitialize()
        dispatch = self._git.GetInterfaceFromGlobal(self._git_cookie, pythoncom.IID_IDispatch)
        telescope = win32com.client.Dispatch(dispatch)
        self._local.telescope = telescope
        return telescope

    @telescope.setter
    def telescope(self, value):
        self._local.telescope = value

    def disconnect(self):
        if not self.telescope:
            return
        try:
            self.set_ra_rate(0.0, dry_run=False, force=True)
        except Exception as e:
            self.logger(f"WARNING: could not reset RightAscensionRate to 0 on exit: {e}")
        try:
            self.telescope.Connected = False
        except Exception:
            pass
        if self._git is not None and self._git_cookie is not None:
            try:
                self._git.RevokeInterfaceFromGlobal(self._git_cookie)
            except Exception:
                pass
        self._git = None
        self._git_cookie = None
        self.connected = False

    def get_ra_rate(self):
        return self.telescope.RightAscensionRate

    def get_side_of_pier(self):
        try:
            return self.telescope.SideOfPier
        except Exception:
            return None

    def get_right_ascension(self):
        """Current mount Right Ascension in hours, or None if unavailable."""
        try:
            return self.telescope.RightAscension
        except Exception:
            return None

    def get_declination(self):
        """Current target Declination in degrees, or None if unavailable.
        Needed to correctly convert an angular drift rate (arcsec/s, from
        the guide camera) into RightAscensionRate's actual units -- RA is a
        time coordinate, so one RA-second only equals 15.041" of real sky
        motion at the celestial equator; elsewhere it's scaled by cos(dec)."""
        try:
            return self.telescope.Declination
        except Exception:
            return None

    def get_tracking(self):
        """Whether the mount is currently tracking, or None if the driver
        doesn't report it. Used to gate whether adjustments are computed
        or maintained at all -- PHD2 guiding without the mount tracking
        means there's no meaningful rate to apply, and correcting a mount
        that isn't tracking wouldn't do anything anyway."""
        try:
            return self.telescope.Tracking
        except Exception:
            return None

    def set_ra_rate(self, value, dry_run, force=False):
        # CanSetRightAscensionRate is unreliable on this driver (confirmed
        # empirically) -- we attempt the set directly rather than checking it.
        value = max(-self.max_rate_magnitude, min(self.max_rate_magnitude, value))
        if dry_run and not force:
            self.logger(f"[DRY RUN] Would set RightAscensionRate = {value:.4f}")
            return
        self.telescope.RightAscensionRate = value
        self.logger(f"Set RightAscensionRate = {value:.4f}")
