"""Execution and background HTTP server tools for local application serving."""

from __future__ import annotations

import functools
import http.server
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from schemas.project_results import ExecutionResult, StageFailure, StageStatus
from tools.file_tools import PROJECT_DIR

LOGGER = logging.getLogger(__name__)


def find_free_port(preferred: int = 8000) -> int:
    """Find a free TCP port, trying preferred port first."""
    for port in (preferred, 8080, 8888, 8001, 8002):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Simple HTTP request handler that does not spam stdout."""

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.debug(format, *args)


class LocalServerManager:
    """Singleton-style background static HTTP server manager."""

    _instance: LocalServerManager | None = None
    _lock = threading.Lock()

    def __init__(self, serve_dir: Path | None = None, port: int | None = None) -> None:
        self.serve_dir = (serve_dir or PROJECT_DIR).resolve()
        self.port = port
        self.httpd: http.server.HTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self._running = False

    @classmethod
    def get_instance(cls, serve_dir: Path | None = None) -> LocalServerManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = LocalServerManager(serve_dir=serve_dir)
            elif serve_dir is not None:
                cls._instance.serve_dir = serve_dir.resolve()
            return cls._instance

    def is_running(self) -> bool:
        return self._running and self.httpd is not None

    def start(self, port: int = 8000) -> int:
        """Start background HTTP server if not already running."""
        with self._lock:
            if self._running and self.httpd is not None and self.port is not None:
                return self.port

            actual_port = find_free_port(port)
            self.port = actual_port
            handler_factory = functools.partial(QuietHTTPRequestHandler, directory=str(self.serve_dir))
            self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", actual_port), handler_factory)

            self.server_thread = threading.Thread(
                target=self.httpd.serve_forever,
                name="AI-Dev-StaticServer",
                daemon=True,
            )
            self.server_thread.start()
            self._running = True
            LOGGER.info("Started local static server at http://127.0.0.1:%d/ serving %s", actual_port, self.serve_dir)
            return actual_port

    def stop(self) -> None:
        with self._lock:
            if self.httpd is not None:
                try:
                    self.httpd.shutdown()
                    self.httpd.server_close()
                except Exception as exc:
                    LOGGER.warning("Error stopping local static server: %s", exc)
                self.httpd = None
                self.server_thread = None
                self._running = False

    def get_project_url(self, project_name: str) -> str:
        if not self.is_running():
            self.start()
        return f"http://127.0.0.1:{self.port}/{project_name}/"


class ApplicationExecutor:
    """Starts generated web projects (static or backend) and detects startup failures."""

    def __init__(self, server_manager: LocalServerManager | None = None) -> None:
        self.server_manager = server_manager or LocalServerManager.get_instance()
        self.backend_processes: list[subprocess.Popen] = []

    def execute(self, project_dir: Path, project_name: str) -> ExecutionResult:
        """Inspect project and start the application, returning ExecutionResult."""
        project_dir = project_dir.resolve()
        if not project_dir.is_dir():
            return ExecutionResult(
                status=StageStatus.FAIL,
                app_type="static",
                failure=StageFailure(
                    error_type="MissingProjectDirectory",
                    message=f"Project directory {project_dir} does not exist.",
                    stage="Execute",
                    affected_files=[],
                    evidence=f"Path not found: {project_dir}",
                    suggested_action="Ensure Developer agent writes files into the project directory.",
                ),
            )

        # Detect backend Python / Node app vs static web app
        flask_app = project_dir / "app.py"
        python_main = project_dir / "main.py"
        package_json = project_dir / "package.json"

        if flask_app.is_file() or python_main.is_file():
            entry_file = flask_app if flask_app.is_file() else python_main
            return self._start_backend_process([sys.executable, str(entry_file)], project_dir, project_name)

        if package_json.is_file() and (project_dir / "server.js").is_file():
            return self._start_backend_process(["node", "server.js"], project_dir, project_name)

        # Static web application
        index_file = project_dir / "index.html"
        if not index_file.is_file():
            return ExecutionResult(
                status=StageStatus.FAIL,
                app_type="static",
                failure=StageFailure(
                    error_type="MissingIndexHtml",
                    message="Static web application is missing index.html.",
                    stage="Execute",
                    affected_files=["index.html"],
                    evidence=f"Directory contents: {[p.name for p in project_dir.iterdir()]}",
                    suggested_action="Create index.html in the project root.",
                ),
            )

        port = self.server_manager.start()
        running_url = f"http://127.0.0.1:{port}/{project_name}/"
        return ExecutionResult(
            status=StageStatus.PASS,
            app_type="static",
            running_url=running_url,
            stdout="Local static server running.",
            stderr="",
            exit_code=0,
        )

    def _start_backend_process(self, command: list[str], project_dir: Path, project_name: str) -> ExecutionResult:
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(project_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.backend_processes.append(proc)
            time.sleep(1.0)
            poll = proc.poll()
            if poll is not None and poll != 0:
                stdout, stderr = proc.communicate(timeout=2)
                return ExecutionResult(
                    status=StageStatus.FAIL,
                    app_type="backend",
                    exit_code=poll,
                    stdout=stdout[:2000],
                    stderr=stderr[:2000],
                    failure=StageFailure(
                        error_type="BackendStartupFailed",
                        message=f"Backend process exited immediately with code {poll}.",
                        stage="Execute",
                        affected_files=[command[1] if len(command) > 1 else ""],
                        evidence=stderr[:1000] or stdout[:1000],
                        suggested_action="Fix imports, dependencies, or port conflicts.",
                    ),
                )
            running_url = "http://127.0.0.1:5000/"
            return ExecutionResult(
                status=StageStatus.PASS,
                app_type="backend",
                running_url=running_url,
                stdout="Backend process running.",
                stderr="",
                exit_code=None,
            )
        except Exception as exc:
            return ExecutionResult(
                status=StageStatus.FAIL,
                app_type="backend",
                failure=StageFailure(
                    error_type="ProcessLaunchError",
                    message=f"Failed to start backend process: {exc}",
                    stage="Execute",
                    affected_files=[],
                    evidence=str(exc),
                    suggested_action="Check backend startup command and system dependencies.",
                ),
            )
