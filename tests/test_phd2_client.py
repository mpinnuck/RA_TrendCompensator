"""PHD2 client connection lifecycle tests using a local TCP listener."""

import socket
import time

from src.model.phd2_client import PHD2Client


def _unused_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_connects_in_background_when_phd2_starts_later():
    port = _unused_port()
    client = PHD2Client(
        "127.0.0.1", port,
        on_guide_step=lambda _msg: None,
        on_guiding_stopped=lambda: None,
        on_app_state=lambda _state: None,
        logger=lambda _msg: None,
        retry_interval_seconds=0.01,
    )
    client.start()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(1)
    listener.settimeout(1.0)
    try:
        connection, _address = listener.accept()
        try:
            deadline = time.monotonic() + 1.0
            while not client.is_connected and time.monotonic() < deadline:
                time.sleep(0.01)
            assert client.is_connected
        finally:
            connection.close()
    finally:
        client.stop()
        listener.close()