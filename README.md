# RA Trend Compensator

**RA Trend Compensator** is a Windows desktop application designed for astrophotography. It automatically measures and compensates for systematic Right Ascension (RA) drift in real time by interfacing with **PHD2** guiding software and an **ASCOM** telescope mount.

By using rolling linear regression on live PHD2 guide errors, the application dynamically adjusts the mount's tracking rate (`RightAscensionRate` via ASCOM). This active drift compensation significantly reduces the workload on PHD2's pulse guiding, resulting in smoother guiding and tighter stars during long-exposure astrophotography.

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

Settings can be edited via the application's GUI (**Settings...** button) or directly in `config.json`:

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `phd2_host` | `"localhost"` | Hostname or IP address where PHD2 is running |
| `phd2_port` | `4400` | PHD2 Event Server port |
| `ascom_prog_id` | `"ASCOM.ASIMount.Telescope"` | ProgID of your ASCOM telescope driver |
| `dry_run` | `true` | When true, logs rate adjustments without applying them to the mount |
| `window_seconds` | `300` | Rolling window length (seconds) for calculating trend slope |
| `min_samples_for_trend` | `60` | Minimum guide step samples required before calculating drift |
| `apply_interval_seconds` | `120` | Interval between rate adjustments |
| `damping_factor` | `0.3` | Damping factor applied to rate corrections to prevent overshooting |
| `max_rate_magnitude` | `1.0` | Maximum allowed `RightAscensionRate` offset limit |
| `max_step_per_cycle` | `0.05` | Maximum rate change allowed per single adjustment cycle |
| `pixel_scale_arcsec` | `0.51` | Camera pixel scale (arcseconds per pixel) |
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

Each line includes `running`, `phd2_connected`, `dry_run`, `current_offset`, current guide/trend/RMS measurements, `declination_deg`, `side_of_pier`, and a Unix `timestamp`. `side_of_pier` is rendered as `"East"`, `"West"`, or `"Unknown"` for external display.

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

## Recent Updates

- Version `1.6.0` adds a live status-client count in the main toolbar.
- PHD2 connection retries now run in the background and recover from PHD2 restarts.
- CSV logs retain ASCOM's numeric pier-side values (`0` or `1`); user-facing status and flip logs show `East` or `West`.

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
