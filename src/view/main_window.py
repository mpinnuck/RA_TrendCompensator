"""Tkinter View: status/controls fixed at top, then a resizable vertical split
between the live RA drift chart and the scrolling log panel."""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from src.view.drift_chart import DriftChartPanel
from src.view.settings_dialog import SettingsDialog

LOG_POLL_MS = 250
CHART_POLL_MS = 1000
APP_VERSION = "4.1.0"


class MainWindow(tk.Tk):
    def __init__(self, view_model):
        super().__init__()
        self.vm = view_model

        self.title("RA Trend Compensator")
        self.minsize(700, 500)
        self._build_widgets()
        self._center_on_screen(1000, 750)
        self.after(100, self._set_initial_sash)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(LOG_POLL_MS, self._poll_log_queue)
        self.after(CHART_POLL_MS, self._poll_chart)

        if self.vm.config.get("autostart", False):
            # Deferred via after() rather than called directly here so the
            # window is fully constructed and visible first -- matches how
            # a person clicking Start would experience it, and avoids
            # starting before the log/chart pollers above are wired up.
            self.after(200, self._on_start)

    # -- layout ---------------------------------------------------------

    def _center_on_screen(self, width, height):
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_widgets(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        controls = ttk.Frame(self, padding=10)
        controls.grid(row=0, column=0, sticky="ew")

        self.start_stop_button = tk.Button(
            controls,
            text="Start",
            command=self._on_start_stop,
            padx=12,
            pady=4,
            bg="#edf2f7",
            fg="#1f2d3d",
            activebackground="#dfe9f4",
            activeforeground="#1f2d3d",
            borderwidth=1,
            relief="raised",
            highlightthickness=0,
        )
        self.start_stop_button.grid(row=0, column=0, padx=(0, 5))

        self.settings_button = ttk.Button(
            controls,
            text="Settings...",
            command=self._on_settings,
        )
        self.settings_button.grid(row=0, column=1, padx=5)

        self.dry_run_var = tk.BooleanVar(value=self.vm.dry_run)
        self.dry_run_check = ttk.Checkbutton(
            controls, text="Dry run", variable=self.dry_run_var, command=self._on_dry_run_toggle
        )
        self.dry_run_check.grid(row=0, column=2, padx=5)

        self.status_var = tk.StringVar(value="Stopped")
        ttk.Label(controls, text="Status:").grid(row=0, column=3, padx=(15, 5))
        ttk.Label(controls, textvariable=self.status_var).grid(row=0, column=4, sticky="w")
        controls.grid_columnconfigure(4, weight=1)

        self.phd2_status_label = tk.Label(
            controls,
            text="PHD2",
            bg="#edf2f7",
            fg="#1f2d3d",
            padx=10,
            pady=3,
            relief="raised",
            borderwidth=1,
            highlightthickness=0,
        )
        self.phd2_status_label.grid(row=0, column=5, padx=(15, 5))

        self.mount_status_label = tk.Label(
            controls,
            text="Mount",
            bg="#edf2f7",
            fg="#1f2d3d",
            padx=10,
            pady=3,
            relief="raised",
            borderwidth=1,
            highlightthickness=0,
        )
        self.mount_status_label.grid(row=0, column=6, padx=(0, 5))

        self.status_clients_var = tk.StringVar(value="Status clients: 0")
        self.status_clients_label = tk.Label(
            controls,
            textvariable=self.status_clients_var,
            bg="#edf2f7",
            fg="#1f2d3d",
            padx=10,
            pady=3,
            relief="raised",
            borderwidth=1,
            highlightthickness=0,
        )
        self.status_clients_label.grid(row=0, column=7, padx=(15, 5))
        ttk.Label(controls, text=f"V {APP_VERSION}", font=("TkDefaultFont", 8)).grid(
            row=0, column=8, sticky="e"
        )

        self._refresh_status_indicators()

        self.mount_coordinates_var = tk.StringVar(value="Mount RA: --  Dec: --")
        ttk.Label(controls, textvariable=self.mount_coordinates_var).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

        self.offset_var = tk.StringVar(value="RightAscensionRate offset: 0.0000")
        ttk.Label(controls, textvariable=self.offset_var).grid(
            row=1, column=1, columnspan=6, sticky="w", padx=(20, 0), pady=(8, 0)
        )

        # Vertical split: drift chart on top, log panel below. Both panes get
        # equal weight and we set the sash to the midpoint once the window is
        # realized, so it defaults to a 50/50 top/bottom split like PHD2's
        # graph area -- the user can still drag the sash to resize either way.
        self.paned = ttk.PanedWindow(self, orient="vertical")
        self.paned.grid(row=1, column=0, sticky="nsew")

        chart_frame = ttk.Frame(self.paned, padding=(10, 0, 10, 5))
        self.chart = DriftChartPanel(
            chart_frame,
            history_hours=self.vm.config["chart_history_hours"],
            on_clear=self._on_clear_graph,
        )
        self.chart.pack(fill="both", expand=True)
        self.paned.add(chart_frame, weight=1)

        log_frame = ttk.Frame(self.paned, padding=(10, 5, 10, 10))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        self.log_panel = scrolledtext.ScrolledText(
            log_frame, wrap="word", state="disabled", font=("Consolas", 9)
        )
        self.log_panel.grid(row=0, column=0, sticky="nsew")
        self.paned.add(log_frame, weight=1)

    def _set_initial_sash(self):
        self.update_idletasks()
        total_height = self.paned.winfo_height()
        if total_height > 1:
            self.paned.sashpos(0, total_height // 2)

    # -- event handlers ---------------------------------------------------

    def _on_start_stop(self):
        if self.vm.running:
            self._on_stop()
        else:
            self._on_start()

    def _on_start(self):
        try:
            self.vm.start()
        except Exception as e:
            self._append_log(f"ERROR starting: {e}")
            return
        self.status_var.set("Running (Simulation)" if self.vm.config.get("simulation_mode") else "Running")
        self.start_stop_button.config(
            text="Stop",
            bg="#2e9d5d",
            fg="white",
            activebackground="#2e9d5d",
            activeforeground="white",
        )
        self.settings_button.config(state="disabled")

    def _on_stop(self):
        self.vm.stop()
        self.status_var.set("Stopped")
        self.start_stop_button.config(
            text="Start",
            bg="#edf2f7",
            fg="#1f2d3d",
            activebackground="#dfe9f4",
            activeforeground="#1f2d3d",
        )
        self.settings_button.config(state="normal")

    def _on_dry_run_toggle(self):
        self.vm.set_dry_run(self.dry_run_var.get())

    def _on_clear_graph(self):
        self.vm.clear_drift_history()

    def _on_settings(self):
        SettingsDialog(self, dict(self.vm.config), self._on_settings_saved)

    def _on_settings_saved(self, new_config):
        try:
            self.vm.update_config(new_config)
        except Exception as e:
            messagebox.showerror("Settings", f"Could not apply settings: {e}")
            return
        self.chart.set_history_hours(new_config["chart_history_hours"])

    def _on_close(self):
        self.vm.shutdown()
        self.destroy()

    # -- polling ------------------------------------------------------------

    def _refresh_status_indicators(self):
        phd2_connected = bool(getattr(getattr(self.vm, "phd2", None), "is_connected", False))
        mount_connected = bool(getattr(getattr(self.vm, "mount", None), "connected", False))

        self.phd2_status_label.config(
            bg="#2e9d5d" if phd2_connected else "#d9534f",
            fg="white",
        )
        self.mount_status_label.config(
            bg="#2e9d5d" if mount_connected else "#d9534f",
            fg="white",
        )

        client_count = self.vm.get_status_client_count()
        if client_count > 0:
            self.status_clients_var.set(f"Status clients: {client_count}")
            self.status_clients_label.config(bg="#2e9d5d", fg="white")
        else:
            self.status_clients_var.set(f"Status clients: {client_count}")
            self.status_clients_label.config(bg="#edf2f7", fg="#1f2d3d")

    def _poll_log_queue(self):
        for line in self.vm.drain_log_queue():
            self._append_log(line)
        self.offset_var.set(f"RightAscensionRate offset: {self.vm.current_offset:+.4f}")
        self._refresh_status_indicators()
        self.after(LOG_POLL_MS, self._poll_log_queue)

    def _poll_chart(self):
        samples, rate_changes = self.vm.get_drift_snapshot()
        self.chart.update_data(samples, rate_changes)
        right_ascension, declination = self.vm.get_mount_coordinates()
        ra_text = f"{right_ascension:.4f} h" if right_ascension is not None else "--"
        dec_text = f"{declination:+.2f} deg" if declination is not None else "--"
        self.mount_coordinates_var.set(f"Mount RA: {ra_text}  Dec: {dec_text}")
        self.after(CHART_POLL_MS, self._poll_chart)

    def _append_log(self, line):
        self.log_panel.config(state="normal")
        self.log_panel.insert("end", line + "\n")
        self.log_panel.see("end")
        self.log_panel.config(state="disabled")
