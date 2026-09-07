"""Unit tests for StatusServer -- a local-only TCP server that pushes
newline-delimited JSON status snapshots to any connected client, for
external tools (e.g. a future NINA plugin) to monitor the compensator.

Uses port=0 (OS-assigned free port) throughout, so tests never collide on
a fixed port and can run concurrently or in quick succession safely."""

import json
import socket
import time

import pytest

from src.model.status_server import StatusServer


def _connect(server, timeout=2.0):
    conn = socket.create_connection((server.host, server.port), timeout=timeout)
    return conn


def _read_one_json_line(conn, timeout=2.0):
    conn.settimeout(timeout)
    buf = b""
    while b"\n" not in buf:
        chunk = conn.recv(4096)
        if not chunk:
            raise ConnectionError("server closed the connection before sending a line")
        buf += chunk
    line, _, _rest = buf.partition(b"\n")
    return json.loads(line.decode("utf-8"))


@pytest.fixture
def server():
    logs = []
    srv = StatusServer(
        host="127.0.0.1", port=0,
        get_snapshot=lambda: {"hello": "world"},
        interval_seconds=0.05,
        logger=logs.append,
    )
    srv.start()
    yield srv
    srv.stop()


def test_client_receives_a_status_snapshot(server):
    conn = _connect(server)
    try:
        data = _read_one_json_line(conn)
        assert data == {"hello": "world"}
    finally:
        conn.close()


def test_multiple_clients_all_receive_snapshots(server):
    conn1 = _connect(server)
    conn2 = _connect(server)
    try:
        assert _read_one_json_line(conn1) == {"hello": "world"}
        assert _read_one_json_line(conn2) == {"hello": "world"}
    finally:
        conn1.close()
        conn2.close()


def test_snapshot_reflects_live_changes():
    state = {"value": 1}
    srv = StatusServer(
        host="127.0.0.1", port=0, get_snapshot=lambda: dict(state),
        interval_seconds=0.05, logger=lambda msg: None,
    )
    srv.start()
    try:
        conn = _connect(srv)
        try:
            assert _read_one_json_line(conn)["value"] == 1
            state["value"] = 2
            # Drain until we see the updated value (broadcasts are periodic).
            deadline = time.time() + 2.0
            seen = None
            while time.time() < deadline:
                seen = _read_one_json_line(conn)
                if seen["value"] == 2:
                    break
            assert seen["value"] == 2
        finally:
            conn.close()
    finally:
        srv.stop()


def test_disconnected_client_does_not_crash_subsequent_broadcasts(server):
    conn = _connect(server)
    _read_one_json_line(conn)
    conn.close()  # disconnect without telling the server

    time.sleep(0.2)  # let a broadcast attempt hit the now-dead socket

    # A fresh client should still work fine afterwards.
    conn2 = _connect(server)
    try:
        data = _read_one_json_line(conn2)
        assert data == {"hello": "world"}
    finally:
        conn2.close()


def test_snapshot_provider_error_does_not_crash_the_server():
    calls = {"n": 0}

    def flaky_snapshot():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {"ok": True}

    logs = []
    srv = StatusServer(
        host="127.0.0.1", port=0, get_snapshot=flaky_snapshot,
        interval_seconds=0.05, logger=logs.append,
    )
    srv.start()
    try:
        conn = _connect(srv)
        try:
            data = _read_one_json_line(conn)  # should skip the failing first attempt
            assert data == {"ok": True}
        finally:
            conn.close()
    finally:
        srv.stop()

    assert any("WARNING" in line for line in logs)


def test_stop_closes_connected_clients(server):
    conn = _connect(server)
    server.stop()
    conn.settimeout(2.0)
    # Either recv returns empty (clean close) or raises -- both indicate closed.
    try:
        data = conn.recv(4096)
        assert data == b""
    except OSError:
        pass
    finally:
        conn.close()


def test_client_count_tracks_connections(server):
    assert server.client_count() == 0
    conn = _connect(server)
    try:
        time.sleep(0.1)  # let the accept loop register it
        assert server.client_count() == 1
    finally:
        conn.close()
