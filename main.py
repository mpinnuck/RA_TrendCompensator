r"""Entry point: load config, build the ViewModel, launch the View.

Run this from the project root (RA_TrendCompensator/):
    python main.py

Build
.venv\Scripts\Activate.ps1
pyinstaller --noconfirm --clean ra_trend_compensator.spec 
copy dist\RA_TrendCompensator.exe C:\D_Drive\Astro\apps\RATrendCompensator\

"""

import argparse

from src.config import load_config
from src.single_instance import SingleInstance, focus_existing_instance
from src.viewmodel.view_model import RATrendCompensatorViewModel
from src.view.main_window import MainWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run RA Trend Compensator.")
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="start the main window minimized",
    )
    args = parser.parse_args(argv)

    instance = SingleInstance()
    if not instance.acquire():
        focus_existing_instance()
        return

    try:
        config = load_config()
        view_model = RATrendCompensatorViewModel(config)
        app = MainWindow(view_model)
        if args.minimized:
            app.after_idle(app.iconify)
        app.mainloop()
    finally:
        instance.release()


if __name__ == "__main__":
    main()
