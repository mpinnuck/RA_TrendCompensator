from unittest.mock import Mock, patch

from src.single_instance import ERROR_ALREADY_EXISTS, SingleInstance, focus_existing_instance


def test_non_windows_always_allows_instance():
    instance = SingleInstance()

    with patch("src.single_instance.os.name", "posix"):
        assert instance.acquire() is True


def test_windows_rejects_existing_mutex():
    kernel32 = Mock()
    kernel32.CreateMutexW.return_value = 42

    with patch("src.single_instance.os.name", "nt"), patch(
        "src.single_instance.ctypes.WinDLL", return_value=kernel32
    ), patch("src.single_instance.ctypes.get_last_error", return_value=ERROR_ALREADY_EXISTS):
        instance = SingleInstance()

        assert instance.acquire() is False

    kernel32.CloseHandle.assert_called_once_with(42)


def test_windows_focuses_existing_window_without_showing_message():
    user32 = Mock()
    user32.FindWindowW.return_value = 99

    with patch("src.single_instance.os.name", "nt"), patch(
        "src.single_instance.ctypes.WinDLL", return_value=user32
    ):
        focus_existing_instance()

    user32.FindWindowW.assert_called_once_with(None, "RA Trend Compensator")
    user32.ShowWindow.assert_called_once_with(99, 9)
    user32.SetForegroundWindow.assert_called_once_with(99)