"""Entry point: load config, build the ViewModel, launch the View.

Run this from the project root (RA_TrendCompensator/):
    python main.py
"""

from src.config import load_config
from src.viewmodel.view_model import RATrendCompensatorViewModel
from src.view.main_window import MainWindow


def main():
    config = load_config()
    view_model = RATrendCompensatorViewModel(config)
    app = MainWindow(view_model)
    app.mainloop()


if __name__ == "__main__":
    main()
