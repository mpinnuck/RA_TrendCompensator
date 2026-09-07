"""Modal Settings dialog: edits the config values that aren't already on the
main toolbar (dry run stays there since it's meant to be toggled live).

Text-entry based, validated on Save. Values are parsed to the same types
used in config.py's DEFAULTS, so a bad entry (e.g. non-numeric port) is
caught here rather than surfacing later as a stack trace.
"""

import tkinter as tk
from tkinter import filedialog, ttk

from src.model.real_session_profiles import PROFILE_TARGETS, PROFILES


class SettingsDialog(tk.Toplevel):
    # (config key, checkbox label)
    CHECKBOX_FIELDS = [
        ("simulation_mode", "Simulation mode (synthetic drift data -- no PHD2 or mount hardware)"),
        ("status_server_enabled", "Status server (local-only, for external tools e.g. a NINA plugin)"),
    ]

    # (config key, display label, type to parse the entry into) -- grouped
    # into sections, which _build_widgets lays out side by side (columns)
    # rather than stacked, so the dialog grows wide instead of tall and the
    # Save button stays on screen.
    SECTIONS = [
        ("General", [
            ("phd2_host", "PHD2 host", str),
            ("phd2_port", "PHD2 port", int),
            ("ascom_prog_id", "ASCOM ProgID", str),
            ("window_seconds", "Trend window (s)", int),
            ("min_samples_for_trend", "Min samples for trend", int),
            ("apply_interval_seconds", "Apply interval (s)", int),
            ("damping_factor", "Damping factor", float),
            ("rms_window_seconds", "Guide RMS window (s)", int),
            ("rms_trend_window_seconds", "Guide RMS trend window (s)", int),
            ("rms_sample_interval_seconds", "Guide RMS sample interval (s)", int),
            ("max_rate_magnitude", "Max rate magnitude", float),
            ("max_step_per_cycle", "Max step per cycle", float),
            ("pixel_scale_arcsec", "Pixel scale (arcsec/px)", float),
        ]),
        ("Logging & status", [
            ("chart_history_hours", "Chart history (hours)", float),
            ("log_folder", "Log folder (blank = app folder)", str),
            ("log_file", "Log file", str),
            ("data_log_file", "Data log CSV (guide steps + adjustments)", str),
            ("status_server_host", "Status server host", str),
            ("status_server_port", "Status server port", int),
            ("status_server_interval_seconds", "Status server broadcast interval (s)", float),
        ]),
        ("Simulation (requires app stopped)", [
            ("sim_bias_direction", "Sim: bias direction", str),
            ("sim_true_drift_arcsec_per_sec", "Sim: true drift rate (arcsec/s)", float),
            ("sim_drift_walk_std", "Sim: drift random-walk (arcsec/s/step)", float),
            ("sim_drift_ramp_arcsec_per_sec_per_hour", "Sim: drift ramp (arcsec/s per hour)", float),
            ("sim_noise_arcsec", "Sim: guide noise (arcsec)", float),
            ("sim_pull_to_zero_per_step", "Sim: long-term pull-to-zero", float),
            ("sim_guide_step_interval_s", "Sim: guide step interval (s)", float),
            ("sim_speed_multiplier", "Sim: speed multiplier", float),
        ]),
        ("Target & polar alignment (optional)", [
            ("sim_declination_deg", "Sim: declination (deg)", float),
            ("sim_target_name", "Sim: target name", str),
            ("sim_target_ra_hours", "Sim: target RA (hours)", float),
            ("sim_start_hour_angle_hours", "Sim: start hour angle (h)", float),
            ("sim_polar_error_arcmin", "Sim: polar alignment error (arcmin)", float),
            ("sim_polar_error_angle_deg", "Sim: polar error angle (deg)", float),
        ]),
    ]

    # Flat list derived from SECTIONS -- used by _on_save_clicked for parsing.
    FIELDS = [field for _name, fields in SECTIONS for field in fields]

    # The profile controls (Load <name>/Clear buttons) are inserted into this
    # section, directly after the sim_drift_ramp field.
    PROFILE_SECTION = "Simulation (requires app stopped)"

    def __init__(self, parent, config, on_save):
        super().__init__(parent)
        self.config = config
        self.on_save = on_save
        self.vars = {}
        self._drift_profile = config.get("sim_drift_profile")

        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent)

        self._build_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._center_over(parent)
        self.grab_set()

    # -- layout ---------------------------------------------------------

    # Two sections per column: (General, Logging & status) on the left,
    # (Simulation, Target & polar) on the right.
    COLUMNS = [(0, 1), (2, 3)]

    def _build_widgets(self):
        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")

        checkboxes = ttk.Frame(body)
        checkboxes.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        for key, label in self.CHECKBOX_FIELDS:
            var = tk.BooleanVar(value=bool(self.config.get(key, False)))
            ttk.Checkbutton(checkboxes, text=label, variable=var).pack(anchor="w", pady=(0, 2))
            self.vars[key] = var

        for column, section_indexes in enumerate(self.COLUMNS):
            column_frame = ttk.Frame(body, padding=(0 if column == 0 else 18, 0, 0, 0))
            column_frame.grid(row=1, column=column, sticky="new")
            row = 0
            for section_index in section_indexes:
                name, fields = self.SECTIONS[section_index]
                frame = ttk.LabelFrame(column_frame, text=name, padding=10)
                frame.grid(row=row, column=0, sticky="new", pady=(0, 10))
                frame.grid_columnconfigure(1, weight=1)
                row += 1
                self._build_section_fields(frame, name, fields)

        self.error_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=self.error_var, foreground="#c53030", wraplength=720).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(2, 0)
        )

        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.grid(row=1, column=0, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self._on_cancel).pack(side="right")
        ttk.Button(buttons, text="Save", command=self._on_save_clicked).pack(side="right", padx=(0, 8))

    def _build_section_fields(self, frame, section_name, fields):
        """Adds the label/entry rows for one section to its LabelFrame."""
        row = 0
        for key, label, _type in fields:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=str(self.config.get(key, "")))
            if key == "sim_bias_direction":
                ttk.Combobox(
                    frame, textvariable=var, values=["west", "east"], state="readonly", width=25
                ).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=2)
            elif key == "log_folder":
                ttk.Entry(frame, textvariable=var, width=28).grid(
                    row=row, column=1, sticky="ew", padx=(10, 0), pady=2
                )
                ttk.Button(frame, text="...", width=3, command=self._browse_log_folder).grid(
                    row=row, column=2, sticky="w", padx=(6, 0), pady=2
                )
            else:
                ttk.Entry(frame, textvariable=var, width=28).grid(
                    row=row, column=1, sticky="ew", padx=(10, 0), pady=2
                )
            self.vars[key] = var
            row += 1

            if key == "sim_bias_direction":
                ttk.Label(
                    frame,
                    text="(true drift rate/ramp below are treated as magnitudes -- this sets their sign)",
                    foreground="#718096", wraplength=330,
                ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 6))
                row += 1

            if key == "sim_drift_ramp_arcsec_per_sec_per_hour" and section_name == self.PROFILE_SECTION:
                row = self._build_profile_controls(frame, row)

    def _build_profile_controls(self, body, row):
        """Convenience controls for loading/clearing a real, log-derived
        drift profile (see real_session_profiles.py) in place of the
        constant/ramp fields above -- a profile, when loaded, overrides
        them for the true-drift baseline."""
        ttk.Label(body, text="Real session profile").grid(row=row, column=0, sticky="w", pady=2)
        self.profile_status_var = tk.StringVar()
        ttk.Label(body, textvariable=self.profile_status_var, foreground="#2b6cb0").grid(
            row=row, column=1, sticky="w", padx=(10, 0), pady=2
        )
        row += 1

        profile_buttons = ttk.Frame(body)
        profile_buttons.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
        for name in PROFILES:
            ttk.Button(
                profile_buttons, text=f"Load {name}", command=lambda n=name: self._load_profile(n)
            ).pack(side="left")
        ttk.Button(profile_buttons, text="Clear profile", command=self._clear_profile).pack(
            side="left", padx=(8, 0)
        )
        row += 1

        ttk.Label(
            body, text="(loading also sets target/declination/hour-angle below to match the source session)",
            foreground="#718096", wraplength=330,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 6))
        row += 1

        self._update_profile_status()
        return row

    def _update_profile_status(self):
        if self._drift_profile:
            self.profile_status_var.set(f"loaded ({len(self._drift_profile)} points)")
        else:
            self.profile_status_var.set("none")

    def _load_profile(self, name):
        self._drift_profile = list(PROFILES[name])
        self._update_profile_status()
        target = PROFILE_TARGETS.get(name, {})
        for config_key, target_key in (
            ("sim_declination_deg", "dec_deg"),
            ("sim_target_name", "name"),
            ("sim_target_ra_hours", "ra_hours"),
            ("sim_start_hour_angle_hours", "start_hour_angle_hours"),
        ):
            if target_key in target and config_key in self.vars:
                self.vars[config_key].set(str(target[target_key]))

    def _browse_log_folder(self):
        folder = filedialog.askdirectory(parent=self, title="Select log folder")
        if folder:  # empty string = dialog cancelled, leave the entry alone
            self.vars["log_folder"].set(folder)

    def _clear_profile(self):
        self._drift_profile = None
        self._update_profile_status()

    def _center_over(self, parent):
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    # -- actions ----------------------------------------------------------

    def _on_cancel(self):
        self.grab_release()
        self.destroy()

    def _on_save_clicked(self):
        new_config = dict(self.config)

        for key, _label in self.CHECKBOX_FIELDS:
            new_config[key] = bool(self.vars[key].get())

        for key, label, field_type in self.FIELDS:
            raw = self.vars[key].get().strip()
            try:
                new_config[key] = field_type(raw)
            except ValueError:
                self.error_var.set(f"'{label}' must be a valid {field_type.__name__}.")
                return

        new_config["sim_drift_profile"] = self._drift_profile

        self.error_var.set("")
        self.grab_release()
        self.destroy()
        self.on_save(new_config)
