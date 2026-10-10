"""Reusable, limited tools for the new workflow agents."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool


class WriteJsonResultTool(BaseTool):
    name: str = "write_json_result"
    description: str = "Write a structured result as JSON to the project state directory."

    def _run(self, filename: str, value: dict[str, Any]) -> str:
        root = Path(os.environ.get("AI_DEV_PROJECT_ROOT", os.getcwd())) / "output"
        target = (root / filename).resolve()
        if not target.is_relative_to(root.resolve()):
            return "ERROR: path escapes output directory"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2), encoding="utf-8")
        return f"OK: wrote {filename}"
