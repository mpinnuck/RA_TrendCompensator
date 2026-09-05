"""MainWindow tests -- verify the compact control-strip state changes."""

import pytest

tk = pytest.importorskip("tkinter")
from tkinter import ttk

from src.view.main_window import APP_VERSION, MainWindow


class FakeViewModel:
    def __init__(self):
        self.config = {"chart_history_hours": 8, "simulation_mode": False}
        self.dry_run = False
        self.running = False
        self.current_offset = 0.0

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def drain_log_queue(self):
        return []

    def get_drift_snapshot(self):
        return [], []

    def set_dry_run(self, dry_run):
        self.dry_run = dry_run


@pytest.fixture
def main_window():
    window = MainWindow(FakeViewModel())
    window.withdraw()
    yield window
    window.destroy()


def test_start_stop_button_turns_green_while_running(main_window):
    main_window._on_start_stop()

    assert main_window.start_stop_button.cget("text") == "Stop"
    assert main_window.start_stop_button.cget("bg") == "green"

    main_window._on_start_stop()

    assert main_window.start_stop_button.cget("text") == "Start"
    assert main_window.status_var.get() == "Stopped"


def test_version_label_is_shown_in_top_right_control_column(main_window):
    version_labels = [
        child for child in main_window.winfo_children()[0].winfo_children()
        if isinstance(child, ttk.Label) and child.cget("text") == f"V {APP_VERSION}"
    ]

    assert len(version_labels) == 1
    assert version_labels[0].grid_info()["column"] == 5