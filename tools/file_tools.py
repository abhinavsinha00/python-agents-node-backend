import os
import subprocess
from pathlib import Path
from pathlib import PureWindowsPath

from crewai.tools import BaseTool

PROJECT_DIR = Path(os.path.abspath("output")).resolve()


def resolve_output_path(path: str, output_dir: Path = PROJECT_DIR) -> Path:
    """Resolve a relative project path safely beneath the output directory."""
    normalized = path.strip().replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    candidate = Path(normalized)
    if candidate.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("path must be relative to output/")

    parts = list(candidate.parts)
    if any(part == ".." for part in parts):
        raise ValueError("path must not escape output/")
    while parts and parts[0].lower() == "output":
        parts.pop(0)
    if not parts:
        raise ValueError("path must name a file inside output/")

    root = output_dir.resolve()
    resolved = (root / Path(*parts)).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("path must not escape output/")
    return resolved


class WriteFileTool(BaseTool):
    name: str = "write_file"
    description: str = "Write code/content to a file inside the project. Input format: path::content  (path relative to output/ folder)"

    def _run(self, tool_input: str) -> str:
        try:
            path, content = tool_input.split("::", 1)
        except ValueError:
            return "ERROR: input must be 'path::content'"
        try:
            full = resolve_output_path(path)
        except ValueError as exc:
            return f"ERROR: {exc}"
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        try:
            rel = full.relative_to(PROJECT_DIR).as_posix()
        except ValueError:
            rel = full.name
        return f"OK: wrote {rel}"

class RunCommandTool(BaseTool):
    name: str = "run_command"
    description: str = ("Run a shell command inside the project (e.g. run tests: pytest, "
                        "python script.py, or list files). Input: command string")
    def _run(self, command: str) -> str:
        try:
            result = subprocess.run(
                command, shell=True, cwd=PROJECT_DIR,
                capture_output=True, text=True, timeout=120
            )
            out = (result.stdout + result.stderr)[:4000]
            return f"exit_code={result.returncode}\n{out}"
        except (OSError, subprocess.SubprocessError) as exc:
            return f"ERROR: {type(exc).__name__}: {exc}"
