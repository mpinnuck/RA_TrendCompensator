"""Minimal PHD2 Server API client -- connects and streams GuideStep events."""

import json
import socket
import threading
import time


class PHD2Client:
    def __init__(self, host, port, on_guide_step, on_guiding_stopped, on_app_state, logger):
        self.host = host
        self.port = port
        self.on_guide_step = on_guide_step
        self.on_guiding_stopped = on_guiding_stopped
        self.on_app_state = on_app_state
        self.logger = logger
        self._sock = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def _run(self):
        while not self._stop.is_set():
            try:
                self.logger(f"Connecting to PHD2 event server at {self.host}:{self.port} ...")
                self._sock = socket.create_connection((self.host, self.port), timeout=10)
                self._sock.settimeout(1.0)
                self.logger("Connected to PHD2.")
                buffer = ""
                while not self._stop.is_set():
                    try:
                        chunk = self._sock.recv(4096).decode("utf-8", errors="replace")
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            self._handle_line(line)
            except Exception as e:
                if not self._stop.is_set():
                    self.logger(f"PHD2 connection error: {e} -- retrying in 5s")
                    time.sleep(5)

    def _handle_line(self, line):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return

        event = msg.get("Event")
        if event == "GuideStep":
            self.on_guide_step(msg)
        elif event == "GuidingStopped":
            self.on_guiding_stopped()
        elif event == "AppState":
            self.on_app_state(msg.get("State"))
