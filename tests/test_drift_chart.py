"""DriftChartPanel tests -- run against a hidden Tk root, no visible window."""

import time

import pytest
import matplotlib.dates as mdates

tk = pytest.importorskip("tkinter")

from src.view.drift_chart import DriftChartPanel
from src.model.drift_history import DriftHistory


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk is unavailable: {error}")
    r.withdraw()  # headless -- don't flash a window during test runs
    yield r
    r.destroy()


@pytest.fixture
def panel(root):
    p = DriftChartPanel(root, history_hours=8)
    p.pack()
    root.update_idletasks()
    return p


def _fill_history(seconds_span=600, step=5):
    hist = DriftHistory(max_seconds=8 * 3600)
    now = time.time()
    n = seconds_span // step
    for i in range(n):
        ts = now - (n - i) * step
        hist.add_sample(ts, i * 0.01)
        if i % 10 == 0:
            hist.add_rate_change(ts, i * 0.0001)
    return hist.snapshot()


def test_update_data_populates_the_line_and_markers(panel):
    samples, rate_changes = _fill_history()
    panel.update_data(samples, rate_changes)

    assert len(panel.line.get_xdata()) == len(samples)
    assert len(panel._rate_lines) == len(rate_changes)


def test_clear_graph_removes_plotted_data_markers_and_calls_callback(root):
    clear_calls = []
    panel = DriftChartPanel(root, history_hours=8, on_clear=lambda: clear_calls.append(True))
    panel.update_data(*_fill_history())

    panel._on_clear_graph()

    assert clear_calls == [True]
    assert len(panel.line.get_xdata()) == 0
    assert panel._rate_lines == []


def test_simulation_time_axis_shows_simulated_time_of_day(panel):
    panel.update_data([(1_000_000_000, 1.0), (1_000_000_002, 2.0)], [])

    assert panel.ax.get_xlabel() == "Time"
    assert isinstance(panel.ax.xaxis.get_major_formatter(), mdates.ConciseDateFormatter)


def test_scroll_zoom_disables_follow(panel):
    samples, rate_changes = _fill_history()
    panel.update_data(samples, rate_changes)
    assert panel.follow_var.get() is True

    xlim = panel.ax.get_xlim()
    mid = (xlim[0] + xlim[1]) / 2
    event = type("Evt", (), {"inaxes": panel.ax, "xdata": mid, "step": 1})()
    panel._on_scroll(event)

    assert panel.follow_var.get() is False


def test_reset_view_reenables_follow(panel):
    samples, rate_changes = _fill_history()
    panel.update_data(samples, rate_changes)

    xlim = panel.ax.get_xlim()
    mid = (xlim[0] + xlim[1]) / 2
    panel._on_scroll(type("Evt", (), {"inaxes": panel.ax, "xdata": mid, "step": 1})())
    assert panel.follow_var.get() is False

    panel._on_reset_view()
    assert panel.follow_var.get() is True


def test_drag_pan_disables_follow(panel):
    samples, rate_changes = _fill_history()
    panel.update_data(samples, rate_changes)

    xlim = panel.ax.get_xlim()
    start = xlim[0] + (xlim[1] - xlim[0]) * 0.6
    end = xlim[0] + (xlim[1] - xlim[0]) * 0.4

    panel._on_press(type("Evt", (), {"inaxes": panel.ax, "xdata": start, "button": 1})())
    panel._on_motion(type("Evt", (), {"inaxes": panel.ax, "xdata": end})())
    panel._on_release(type("Evt", (), {})())

    assert panel.follow_var.get() is False
