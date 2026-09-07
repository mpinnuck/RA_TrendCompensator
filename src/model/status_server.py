"""Local-only TCP status server for external tools (e.g. a future NINA
plugin) to monitor the compensator's live state, without needing to embed
any of its own control logic here.

Mirrors PHD2's own newline-delimited JSON-over-TCP style deliberately --
this app is already a *client* of that protocol (see phd2_client.py), so
pointing the same pattern the other way keeps the whole codebase
consistent rather than introducing a second protocol style.

Read-only by design: this server only ever pushes status snapshots out to
connected clients on a timer. It never reads or acts on anything a client
sends. If two-way control is ever wanted, the intent is to put that logic
in the external tool itself (e.g. the NINA plugin), not split it between
this app and that tool.
"""

import json
import socket
import threading
import time


class StatusServer:
    def __init__(self, host, port, get_snapshot, interval_seconds, logger):
        self.host = host
        self.port = port
        self.get_snapshot = get_snapshot
        self.interval_seconds = interval_seconds
        self.logger = logger

        self._server_socket = None
        self._clients = []
        self._clients_lock = threading.Lock()
        self._stop = threading.Event()
        self._accept_thread = None
        self._broadcast_thread = None

    def start(self):
        self._stop.clear()
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(0.5)
        self.port = self._server_socket.getsockname()[1]  # resolves an OS-assigned port if 0 was requested

        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        self._broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._broadcast_thread.start()
        self.logger(f"[STATUS] Status server listening on {self.host}:{self.port}.")

    def stop(self):
        self._stop.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
        with self._clients_lock:
            for conn in self._clients:
                try:
                    conn.close()
                except OSError:
                    pass
            self._clients.clear()
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2)
        if self._broadcast_thread is not None:
            self._broadcast_thread.join(timeout=2)

    def client_count(self):
        with self._clients_lock:
            return len(self._clients)

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break  # socket was closed by stop()
            with self._clients_lock:
                self._clients.append(conn)

    def _broadcast_loop(self):
        while not self._stop.is_set():
            self._broadcast_once()
            time.sleep(self.interval_seconds)

    def _broadcast_once(self):
        try:
            payload = (json.dumps(self.get_snapshot()) + "\n").encode("utf-8")
        except Exception as e:
            self.logger(f"[STATUS] WARNING: failed to build status snapshot: {e}")
            return

        with self._clients_lock:
            dead = []
            for conn in self._clients:
                try:
                    conn.sendall(payload)
                except OSError:
                    dead.append(conn)
            for conn in dead:
                self._clients.remove(conn)
                try:
                    conn.close()
                except OSError:
                    pass
