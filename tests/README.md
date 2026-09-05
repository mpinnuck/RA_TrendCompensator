# Tests

Fast, hardware-free tests for RA_TrendCompensator. They swap in fakes for
the ASCOM mount and the PHD2 socket client, so no telescope needs to be
connected and no PHD2 instance needs to be running.

## Setup

    pip install -r requirements-dev.txt

## Run

    pytest

Run from the project root -- `conftest.py` puts the project root on
`sys.path` so `import src...` resolves correctly wherever pytest is invoked
from.

## Notes

- `test_drift_chart.py` creates a real (but withdrawn/hidden) Tk window to
  exercise the chart panel, so it needs a display. On Windows or macOS with
  a normal desktop session this just works. On a headless Linux box (e.g.
  CI) run it under a virtual display:

      xvfb-run -a pytest

- The mount and PHD2 client are replaced with lightweight fakes
  (`tests/fakes.py`), so `pywin32` never has to talk to real hardware
  during a test run -- it only needs to be importable.
