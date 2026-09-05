"""Live-updating RA drift strip chart.

Plots raw RA guide error (arcsec) over a rolling time window, marks each
RA-rate change with a dashed vertical line (labelled, PHD2-annotation style),
and supports mouse-driven pan/zoom on the time axis: scroll to zoom, click
and drag to pan. A "Follow live" toggle keeps the view pinned to the most
recent data until the user interacts with the chart, at which point it lets
go so the user can inspect history without fighting live updates.
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

MAX_RATE_LABELS = 12  # thin labels out once more than this many markers are in view


class DriftChartPanel(ttk.Frame):
    def __init__(self, parent, history_hours):
        super().__init__(parent)
        self.window_seconds = history_hours * 3600
        self._pan_start_xdata = None
        self._pan_start_xlim = None
        self._rate_lines = []  # list of dicts: ts, val, dt, vline, text

        self._build_widgets()

    # -- layout ---------------------------------------------------------

    def _build_widgets(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 2))

        self.follow_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            toolbar, text="Follow live", variable=self.follow_var, command=self._on_follow_toggle
        ).pack(side="left")
        ttk.Button(toolbar, text="Reset view", command=self._on_reset_view).pack(side="left", padx=(8, 0))
        ttk.Label(toolbar, text="Scroll to zoom, drag to pan").pack(side="right")

        self.figure = Figure(figsize=(5, 3), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_ylabel("RA guide error (arcsec)")
        self.ax.grid(True, linewidth=0.4, alpha=0.5)
        (self.line,) = self.ax.plot([], [], color="#2b6cb0", linewidth=0.8)
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        self.figure.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.ax.callbacks.connect("xlim_changed", lambda _ax: self._update_rate_labels())

    # -- public API -------------------------------------------------------

    def set_history_hours(self, hours):
        """Updates the rolling window used by 'Follow live' / 'Reset view'.
        Existing plotted data isn't discarded; the ViewModel's own history
        buffer governs how much data actually exists to show."""
        self.window_seconds = hours * 3600

    def update_data(self, samples, rate_changes):
        """Called periodically by the View with the latest snapshot from the ViewModel."""
        if not samples:
            return

        times = [datetime.fromtimestamp(t) for t, _ in samples]
        values = [v for _, v in samples]
        self.line.set_data(times, values)

        self.ax.relim()
        self.ax.autoscale_view(scalex=False, scaley=True)

        self._prune_rate_lines(cutoff=samples[0][0])
        self._add_new_rate_lines(rate_changes)

        if self.follow_var.get():
            self._snap_to_live(samples)

        self._update_rate_labels()
        self.canvas.draw_idle()

    # -- rate-change markers ------------------------------------------------

    def _prune_rate_lines(self, cutoff):
        kept = []
        for entry in self._rate_lines:
            if entry["ts"] < cutoff:
                entry["vline"].remove()
                if entry["text"] is not None:
                    entry["text"].remove()
            else:
                kept.append(entry)
        self._rate_lines = kept

    def _add_new_rate_lines(self, rate_changes):
        known = {e["ts"] for e in self._rate_lines}
        for ts, val in rate_changes:
            if ts in known:
                continue
            dt = datetime.fromtimestamp(ts)
            vline = self.ax.axvline(dt, color="#dd6b20", linewidth=1, linestyle="--", alpha=0.7)
            self._rate_lines.append({"ts": ts, "val": val, "dt": dt, "vline": vline, "text": None})

    def _update_rate_labels(self):
        if not self._rate_lines:
            return
        xlim = self.ax.get_xlim()
        visible = [e for e in self._rate_lines if xlim[0] <= mdates.date2num(e["dt"]) <= xlim[1]]
        step = max(1, len(visible) // MAX_RATE_LABELS) if visible else 1
        labelled_ts = {e["ts"] for i, e in enumerate(visible) if i % step == 0}

        y_top = self.ax.get_ylim()[1]
        for e in self._rate_lines:
            want_label = e["ts"] in labelled_ts
            if want_label:
                if e["text"] is None:
                    e["text"] = self.ax.text(
                        e["dt"], y_top, f"{e['val']:+.3f}",
                        rotation=90, va="top", ha="right", fontsize=7, color="#dd6b20",
                    )
                else:
                    e["text"].set_position((mdates.date2num(e["dt"]), y_top))
            elif e["text"] is not None:
                e["text"].remove()
                e["text"] = None

    # -- follow / reset -------------------------------------------------

    def _snap_to_live(self, samples):
        end = samples[-1][0]
        start = max(samples[0][0], end - self.window_seconds)
        self.ax.set_xlim(datetime.fromtimestamp(start), datetime.fromtimestamp(end))

    def _on_follow_toggle(self):
        if self.follow_var.get():
            self._on_reset_view()

    def _on_reset_view(self):
        self.follow_var.set(True)
        xdata = self.line.get_xdata()
        if len(xdata) == 0:
            return
        end = xdata[-1]
        start = max(xdata[0], datetime.fromtimestamp(end.timestamp() - self.window_seconds))
        self.ax.set_xlim(start, end)
        self.canvas.draw_idle()

    # -- mouse pan / zoom -------------------------------------------------

    def _on_scroll(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return
        cur_xlim = self.ax.get_xlim()
        factor = 0.8 if event.step > 0 else 1.25
        width = (cur_xlim[1] - cur_xlim[0]) * factor
        rel = (event.xdata - cur_xlim[0]) / (cur_xlim[1] - cur_xlim[0])
        self.ax.set_xlim(event.xdata - width * rel, event.xdata + width * (1 - rel))
        self.follow_var.set(False)
        self.canvas.draw_idle()

    def _on_press(self, event):
        if event.inaxes != self.ax or event.button != 1 or event.xdata is None:
            return
        self._pan_start_xdata = event.xdata
        self._pan_start_xlim = self.ax.get_xlim()

    def _on_motion(self, event):
        if self._pan_start_xdata is None or event.inaxes != self.ax or event.xdata is None:
            return
        dx = self._pan_start_xdata - event.xdata
        self.ax.set_xlim(self._pan_start_xlim[0] + dx, self._pan_start_xlim[1] + dx)
        self.follow_var.set(False)
        self.canvas.draw_idle()

    def _on_release(self, _event):
        self._pan_start_xdata = None
        self._pan_start_xlim = None
