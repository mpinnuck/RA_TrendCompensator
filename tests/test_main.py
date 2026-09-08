from unittest.mock import Mock, patch

import main


def test_minimized_option_iconifies_window_after_startup():
    instance = Mock()
    instance.acquire.return_value = True
    app = Mock()

    with patch.object(main, "SingleInstance", return_value=instance), patch.object(
        main, "load_config", return_value={}
    ), patch.object(main, "RATrendCompensatorViewModel"), patch.object(
        main, "MainWindow", return_value=app
    ):
        main.main(["--minimized"])

    app.after_idle.assert_called_once_with(app.iconify)
    app.mainloop.assert_called_once_with()
    instance.release.assert_called_once_with()


def test_second_instance_focuses_existing_window_without_starting_app():
    instance = Mock()
    instance.acquire.return_value = False

    with patch.object(main, "SingleInstance", return_value=instance), patch.object(
        main, "focus_existing_instance"
    ) as focus_existing, patch.object(main, "MainWindow") as main_window:
        main.main(["--minimized"])

    focus_existing.assert_called_once_with()
    main_window.assert_not_called()
    instance.release.assert_not_called()