"""Single-instance enforcement and inter-process communication.

Uses a lock file at ``%APPDATA%/pixiis/daemon.lock`` containing the PID
and a local TCP port.  Other ``pixiis`` processes connect to that port
to send commands (e.g. "show") instead of starting a second daemon.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
from pathlib import Path

from pixiis.core.paths import config_dir


def _lock_path() -> Path:
    return config_dir() / "daemon.lock"


def _is_pid_alive(pid: int) -> bool:
    """Return *True* if a process with *pid* is still running."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class DaemonIPC:
    """Lock file + local TCP socket for single-instance and command passing.

    Lock file contents::

        {"pid": 12345, "port": 54321}

    Other processes connect to ``127.0.0.1:<port>`` to send short text
    commands.  The daemon returns a text response (usually ``"ok"``).
    """

    def __init__(self) -> None:
        self._server: socket.socket | None = None
        self._port: int = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._handler = None  # callable(cmd: str) -> str

    # ── Lock management ────────────────────────────────────────────────

    @staticmethod
    def is_running() -> dict | None:
        """Return lock info ``{"pid": …, "port": …}`` if a daemon is
        alive, otherwise *None*.

        Stale lock files (dead PID) are removed automatically.
        """
        path = _lock_path()
        if not path.exists():
            return None
        try:
            info = json.loads(path.read_text())
            pid, port = info["pid"], info["port"]
        except (json.JSONDecodeError, KeyError, ValueError):
            path.unlink(missing_ok=True)
            return None

        if not _is_pid_alive(pid):
            path.unlink(missing_ok=True)
            return None
        return info

    def acquire(self, handler) -> bool:
        """Start the IPC server and create the lock file.

        *handler* is called as ``handler(cmd) -> str`` for each incoming
        command.  Returns *True* if the lock was acquired successfully.
        """
        if self.is_running() is not None:
            return False

        self._handler = handler

        # Bind to a random available port on localhost
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._port = self._server.getsockname()[1]
        self._server.listen(4)
        self._server.settimeout(1.0)

        # Write lock file (server is already listening at this point)
        _lock_path().write_text(
            json.dumps({"pid": os.getpid(), "port": self._port})
        )

        # Accept connections in a background thread
        self._running = True
        self._thread = threading.Thread(
            target=self._accept_loop, name="daemon-ipc", daemon=True
        )
        self._thread.start()
        return True

    def release(self) -> None:
        """Stop the IPC server and remove the lock file."""
        self._running = False
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        _lock_path().unlink(missing_ok=True)

    # ── Client side ────────────────────────────────────────────────────

    @staticmethod
    def send_command(cmd: str) -> str | None:
        """Send *cmd* to the running daemon and return its response."""
        info = DaemonIPC.is_running()
        if info is None:
            return None
        try:
            with socket.create_connection(
                ("127.0.0.1", info["port"]), timeout=5
            ) as sock:
                sock.sendall(cmd.encode())
                sock.shutdown(socket.SHUT_WR)
                return sock.recv(4096).decode()
        except OSError:
            return None

    # ── Server loop ────────────────────────────────────────────────────

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                data = conn.recv(4096).decode().strip()
                if data and self._handler:
                    resp = self._handler(data) or "ok"
                    conn.sendall(resp.encode())
            except Exception:
                pass
            finally:
                conn.close()
