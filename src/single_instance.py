"""Windows single-instance guard for the desktop application."""

import ctypes
import os


MUTEX_NAME = r"Global\RA_TrendCompensator_SingleInstance"
ERROR_ALREADY_EXISTS = 183
WINDOW_TITLE = "RA Trend Compensator"
SW_RESTORE = 9


class SingleInstance:
    """Own a named system mutex for the lifetime of the application."""

    def __init__(self, name=MUTEX_NAME):
        self.name = name
        self._handle = None

    def acquire(self):
        if os.name != "nt":
            return True

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._handle = kernel32.CreateMutexW(None, True, self.name)
        if not self._handle:
            error = ctypes.get_last_error()
            raise OSError(error, "Could not create the application mutex")

        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(self._handle)
            self._handle = None
            return False

        return True

    def release(self):
        if self._handle is not None:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._handle)
            self._handle = None


def focus_existing_instance():
    """Restore and focus the existing application's main window."""
    if os.name == "nt":
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        window = user32.FindWindowW(None, WINDOW_TITLE)
        if window:
            user32.ShowWindow(window, SW_RESTORE)
            user32.SetForegroundWindow(window)