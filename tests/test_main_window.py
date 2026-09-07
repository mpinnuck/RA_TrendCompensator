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
        self.clear_drift_history_calls = 0

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def drain_log_queue(self):
        return []

    def get_drift_snapshot(self):
        return [], []

    def get_status_client_count(self):
        return 0

    def get_mount_coordinates(self):
        return 19.1628, -63.8

    def set_dry_run(self, dry_run):
        self.dry_run = dry_run

    def clear_drift_history(self):
        self.clear_drift_history_calls += 1


@pytest.fixture
def main_window():
    try:
        window = MainWindow(FakeViewModel())
    except tk.TclError as error:
        pytest.skip(f"Tk is unavailable: {error}")
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


def test_clear_graph_delegates_to_view_model(main_window):
    main_window._on_clear_graph()

    assert main_window.vm.clear_drift_history_calls == 1


def test_version_label_is_shown_in_top_right_control_column(main_window):
    version_labels = [
        child for child in main_window.winfo_children()[0].winfo_children()
        if isinstance(child, ttk.Label) and child.cget("text") == f"V {APP_VERSION}"
    ]

    assert len(version_labels) == 1
    assert version_labels[0].grid_info()["column"] == 6


def test_status_client_count_is_displayed(main_window):
    main_window.vm.get_status_client_count = lambda: 3
    main_window._poll_log_queue()

    assert main_window.status_clients_var.get() == "Status clients: 3"


def test_mount_coordinates_are_displayed_beside_the_offset(main_window):
    main_window._poll_chart()

    assert main_window.mount_coordinates_var.get() == "Mount RA: 19.1628 h  Dec: -63.80 deg"