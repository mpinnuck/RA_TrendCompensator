# RA Trend Compensator

**RA Trend Compensator** is a Windows desktop application designed for astrophotography. It automatically measures and compensates for systematic Right Ascension (RA) drift in real time by interfacing with **PHD2** guiding software and an **ASCOM** telescope mount.

By using rolling linear regression on live PHD2 guide errors, the application dynamically adjusts the mount's tracking rate (`RightAscensionRate` via ASCOM). This active drift compensation significantly reduces the workload on PHD2's pulse guiding, resulting in smoother guiding and tighter stars during long-exposure astrophotography.

---

## Why It Was Developed

This app grew out of a deep-sky imaging session in which an AM5N mount showed a steadily increasing westward bias after a meridian flip. As the bias accumulated, PHD2 had to work progressively harder to keep the mount tracking smoothly. RA Trend Compensator is intended to detect that persistent, one-directional drift early and gently compensate for it at the mount's tracking-rate level.

### How It Works

- The PHD2 client connects to PHD2's documented TCP event server (port `4400` by default) and receives live `GuideStep` events.
- Every guide frame, the trend estimator converts PHD2's `RADistanceRaw` from pixels to arcseconds using the configured pixel scale (default `0.51` arcsec/pixel), then adds the sample to a rolling five-minute window.
- Every two minutes by default, it fits linear regression across that window. A sustained west-bias trend appears as a consistent slope, while normal periodic-error oscillation and back-and-forth guide noise should average toward flat.
- The ASCOM mount controller converts the slope to a `RightAscensionRate` offset. It applies only 30% of the calculated correction per cycle by default and limits each rate step, preventing one noisy fit from causing an abrupt change or overshoot.
- A detected pier-side change (`SideOfPier`) or guiding restart resets the trend window and, when configured, the rate correction because drift behavior can change at those points.
- Dry-run mode calculates and logs every proposed adjustment without changing the mount, so the logic can first be evaluated against real guiding data.

---

## Key Features

- **Live PHD2 Event Integration:** Connects directly to PHD2's socket event server to receive real-time guide step data (`GuideStep` events).
- **ASCOM Mount Tracking Adjustments:** Computes required tracking offsets and updates `RightAscensionRate` on ASCOM-compatible mounts, including automatic Declination cosine scaling ($\cos(\delta)$).
- **Interactive Live Drift Chart:** Built-in Matplotlib strip chart featuring:
  - Real-time rolling RA guide error plot.
  - Vertical annotation markers showing applied rate changes.
  - Interactive pan and scroll-to-zoom capabilities with a "Follow live" toggle.
- **Dry Run Mode:** Safely monitor calculated drift rates and simulated adjustments without sending physical rate commands to the mount.
- **Simulation Mode:** Complete offline testing suite featuring simulated mount movement, configurable drift profiles (polar alignment error, periodic error, random walk, ramps), and simulated PHD2 data feeds.
- **Data & Event Logging:**
  - Human-readable session text log (`ra_trend_compensator.log`).
  - Structured CSV log (`ra_trend_compensator_data.csv`) capturing guide steps and adjustment cycles for quantitative post-session analysis.
- **Local Status Server:** Read-only newline-delimited JSON status feed for external tools such as a NINA plugin.
- **Standalone Executable Support:** Easy PyInstaller build configuration for single-file deployment.

---

## Requirements

- **OS:** Windows 10/11
- **Python:** Python 3.10 or higher
- **Software Dependencies:**
  - [ASCOM Platform](https://ascom-standards.org/) (for live mount connection)
  - [PHD2 Guiding](https://openphdguiding.org/) (with Server enabled)

---

## Installation & Setup

### 1. Clone or Download the Repository

```powershell
git clone https://github.com/your-repo/RA_TrendCompensator.git
cd RA_TrendCompensator
```

### 2. Set Up Virtual Environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

For development and running tests, install dev dependencies as well:

```powershell
pip install -r requirements-dev.txt
```

---

## Configuration

Settings can be edited via the application's GUI (**Settings...** button) or directly in the app's user-data config file.

On Windows, the default config location is:

```text
%LOCALAPPDATA%\RA_TrendCompensator\config.json
```

The application does not depend on its current working directory, which is important when it is launched by NINA or another host. Existing project-local `config.json` files are still accepted as a one-time compatibility fallback when no user-data config exists. Saving settings always writes the user-data config by default.

Logs and CSV data also use `%LOCALAPPDATA%\RA_TrendCompensator\` when `log_folder` is blank. Set `log_folder` to use a specific folder; the folder must be writable or the application falls back to the same user-data directory. Absolute `log_file` and `data_log_file` paths are honored as configured.

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `phd2_host` | `"localhost"` | Hostname or IP address where PHD2 is running |
| `phd2_port` | `4400` | PHD2 Event Server port |
| `ascom_prog_id` | `"ASCOM.ASIMount.Telescope"` | ProgID of your ASCOM telescope driver |
| `dry_run` | `false` | When true, logs rate adjustments without applying them to the mount |
| `window_seconds` | `300` | Rolling window length (seconds) for calculating trend slope |
| `min_samples_for_trend` | `60` | Minimum guide step samples required before calculating drift |
| `apply_interval_seconds` | `120` | Interval between rate adjustments |
| `damping_factor` | `0.3` | Damping factor applied to rate corrections to prevent overshooting |
| `max_rate_magnitude` | `1.0` | Maximum allowed `RightAscensionRate` offset limit |
| `max_step_per_cycle` | `0.05` | Maximum rate change allowed per single adjustment cycle |
| `pixel_scale_arcsec` | `0.51` | Camera pixel scale (arcseconds per pixel) |
| `autostart` | `false` | Start monitoring automatically after the application window is initialized |
| `maintain_interval_seconds` | `60` | Minimum interval between re-sending the last known RA-rate offset while guiding is paused or idle |
| `log_folder` | `""` | Optional folder for log and CSV output; blank uses the application user-data directory |
| `log_file` | `"ra_trend_compensator.log"` | Human-readable text log filename when `log_folder` is used |
| `data_log_file` | `"ra_trend_compensator_data.csv"` | Structured guide-step and adjustment CSV filename when `log_folder` is used |
| `simulation_mode` | `false` | Enable/disable built-in simulation mode for offline testing |
| `status_server_enabled` | `true` | Enable the local, read-only status server |
| `status_server_host` | `"127.0.0.1"` | Interface on which the status server listens; leave local-only unless network access is required |
| `status_server_port` | `4401` | TCP port for status clients |
| `status_server_interval_seconds` | `1.0` | Status broadcast interval while one or more clients are connected |

---

## Status Server

When enabled, the application listens on `127.0.0.1:4401` by default and pushes one JSON object per line to every connected TCP client. The server is read-only: clients do not send commands to the compensator.

For example, PowerShell can display the live feed with:

```powershell
while ($true) {
   $client = [System.Net.Sockets.TcpClient]::new("127.0.0.1", 4401)
   $reader = [System.IO.StreamReader]::new($client.GetStream())
   while (($line = $reader.ReadLine()) -ne $null) { $line }
   $reader.Dispose()
   $client.Dispose()
}
```

Each line includes `running`, `phd2_connected`, `dry_run`, `current_offset`, current guide/trend/RMS measurements, `right_ascension_hours`, `declination_deg`, `side_of_pier`, and a Unix `timestamp`. `side_of_pier` is rendered as `"East"`, `"West"`, or `"Unknown"` for external display.

The server stays available while the app is stopped so an external client can observe application state. It does not build or serialize snapshots while no clients are connected.

---

## Usage

### Running from Source

1. Activate your virtual environment:
   ```powershell
   .venv\Scripts\Activate.ps1
   ```
2. Launch the application:
   ```powershell
   python main.py
   ```
3. In PHD2, ensure **Enable Server** is checked under **Tools** menu.
4. Click **Start** in RA Trend Compensator to begin monitoring and compensating drift.

If PHD2 is not yet running, the app remains running and retries its PHD2 event-server connection in the background every five seconds. It reconnects automatically after PHD2 is started or restarted.

---

## Architecture Diagrams

The project uses PlantUML diagrams maintained alongside the Python source. PlantUML does not automatically infer complete runtime diagrams from Python; when code behavior changes, update the relevant `.puml` source after reviewing the changed classes, callbacks, threads, or execution path.

### VS Code workflow

Install the `jebbs.plantuml` extension, then:

1. Open a diagram source in `diagrams/`.
2. Press `Option+D` from a Mac remote session, or `Alt+D` on Windows, to preview it.
3. Use **PlantUML: Export Current Diagram** to generate the SVG.
4. Review the generated image directly under `diagrams/`.

Workspace settings select local rendering, SVG output, and the `diagrams/` destination. Editable `.puml` sources are kept under `diagrams/puml/`, while generated SVGs are kept directly under `diagrams/` for quick review. Keep both under version control so GitHub can display the rendered documentation.

### Current diagrams

- [Class diagram source](diagrams/puml/ra_trend_compensator_class.puml) | [SVG](diagrams/RA%20Trend%20Compensator%20Class%20Diagram.svg)
- [Startup sequence source](diagrams/puml/startup_sequence.puml) | [SVG](diagrams/Startup%20Sequence.svg)
- [GuideStep compensation source](diagrams/puml/guide_step_sequence.puml) | [SVG](diagrams/Guide%20Step%20Compensation.svg)
- [PHD2 reconnect source](diagrams/puml/phd2_reconnect_sequence.puml) | [SVG](diagrams/PHD2%20Reconnect.svg)
- [Pause and resume source](diagrams/puml/pause_resume_sequence.puml) | [SVG](diagrams/Pause%20Resume.svg)
- [Pier-side reset source](diagrams/puml/pier_flip_sequence.puml) | [SVG](diagrams/Pier%20Flip%20Reset.svg)
- [Simulation mode source](diagrams/puml/simulation_sequence.puml) | [SVG](diagrams/Simulation%20Guide%20Step.svg)
- [Shutdown sequence source](diagrams/puml/shutdown_sequence.puml) | [SVG](diagrams/Shutdown%20Sequence.svg)

Class diagrams describe the application structure. Sequence diagrams describe selected runtime scenarios, including asynchronous PHD2 callbacks, maintenance polling, simulation, and shutdown behavior. After a relevant Python change, update the affected PlantUML source, preview it, validate it, and export a new SVG.

---

## Recent Updates

### NINA Plugin Integration Release

This release adds the core changes needed for a NINA plugin integration while keeping the existing mount-control workflow intact.

- **Auto-start support**: the new `autostart` config key starts the same existing start routine after the window is fully built, avoiding duplicate startup logic.
- **PHD2 pause and resume handling**: the client now reacts to `Settling`, `SettleDone`, `Paused`, and `Resumed` events from PHD2's event-monitoring protocol.
- **Tracking state access**: the mount controller exposes `get_tracking()` with the same defensive error handling as other mount queries, and the simulated mount supports a test hook for tracking-state toggling.
- **Three-state operating model**:
  - **Idle**: mount not tracking, so nothing is computed.
  - **Actively correcting**: tracking, PHD2 guiding, and not paused, preserving the prior behavior.
  - **Maintain**: tracking but not actively correcting; the app periodically re-sends the last known `current_offset` as a safety net during brief interruptions such as dithering or pauses.
  - **Reset**: real pier-side changes clear the offset and trend/RMS state as before, and the maintenance thread now catches these transitions promptly even while guiding is paused.
- **Status snapshot improvements**: `get_status_snapshot()` now includes `phd2_guiding`, `paused`, `mount_tracking`, and `actively_correcting` values for external clients.
- **Settings dialog additions**: the GUI now includes `maintain_interval_seconds` and `autostart` configuration fields. The boolean field is handled as a checkbox rather than a text field to avoid Python's `bool("False") == True` pitfall.
- **Host-safe config and logging paths**: config, text logs, and CSV data default to the per-user application-data directory instead of the process working directory. This prevents NINA-launched sessions from reading or writing an unrelated or protected folder. Configured log folders remain supported, with a writable-path fallback.
- **Thread-safe shared state**: guide-step callbacks, maintenance polling, status snapshots, adjustment calculations, and guiding-stop resets are serialized with a shared state lock. This prevents pier-flip resets and status reads from racing with PHD2 callbacks.
- **Resilient data logging**: the CSV logger checks its destination when opened and during writes, recovering to the per-user application-data directory if the configured location becomes unavailable.

### Compatibility notes

- The actual RA-rate trend calculation remains unchanged: the adjustment logic is still only called from the actively-correcting path.
- Guide-step samples and new rate adjustments are collected only while the mount is tracking, PHD2 is guiding, and compensation is not paused. During a pause or idle period, the last known-good offset may be periodically re-sent without adding new trend samples.
- Simulation mode does not emit pause events because the simulator has no direct concept of them; startup notices alert users to this limitation.
- The application shutdown flow remains unchanged and still resets the mount rate before stopping status services, which keeps NINA's `Process.CloseMainWindow()` behavior working cleanly.

---

## Building the Standalone Executable

To build a standalone single-file `.exe` (`dist/RA_TrendCompensator.exe`):

1. Install PyInstaller:
   ```powershell
   pip install pyinstaller
   ```
2. Run the PyInstaller build:
   ```powershell
   pyinstaller --noconfirm --clean ra_trend_compensator.spec
   ```
3. Copy executable to your target destination:
   ```powershell
   copy dist\RA_TrendCompensator.exe C:\D_Drive\Astro\apps\RATrendCompensator\
   ```

---

## Running Tests

To run the unit test suite:

```powershell
pytest
```

---

## License

MIT License - see `LICENSE` for details.
