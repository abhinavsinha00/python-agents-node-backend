"""Run the isolated mobile CrewAI workflow once with local-only validation."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from providers.llm_config import get_default_llm
from workflows.mobile_workflow import MobileWorkflow
from tools.file_tools import RunCommandTool, WriteFileTool

OUT = Path(__file__).resolve().parent
MODEL = "gemini/gemini-3.5-flash-lite"
REQUIREMENT = "Build a simple mobile Todo application with add task, mark task complete, delete task, local/offline storage, and Home, Add Task, and Settings screens."


class ScopedWriter(WriteFileTool):
    name: str = "write_file"
    description: str = "Write files only inside output/live-mobile-demo. Input path relative to output followed by ::content."

    def _run(self, tool_input: str) -> str:
        try:
            path, content = tool_input.split("::", 1)
        except ValueError:
            return "ERROR: expected path::content"
        target = (ROOT / "output" / path.strip()).resolve()
        if not target.is_relative_to(OUT.resolve()) or target == OUT.resolve():
            return "ERROR: writes are restricted to output/live-mobile-demo"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return "OK: wrote " + target.relative_to(ROOT / "output").as_posix()


class LocalValidationTool(RunCommandTool):
    name: str = "run_command"
    description: str = "Run local syntax, structure, dependency, Expo config, and available prebuild validation exactly once. Exact command: validate live mobile project"
    invoked: bool = False
    results: list[dict] = []

    def _run(self, command: str) -> str:
        if self.invoked or command.strip() != "validate live mobile project":
            return "ERROR: only one exact local validation command is allowed"
        self.invoked = True
        checks = []
        js_files = sorted(OUT.rglob("*.js"))
        node = shutil.which("node")
        syntax_details = []
        syntax_pass = bool(js_files) and bool(node)
        for file in js_files:
            if not node:
                syntax_details.append(file.name + ": Node.js unavailable")
                syntax_pass = False
                continue
            result = subprocess.run([node, "--check", str(file)], cwd=OUT, capture_output=True, text=True, timeout=30)
            syntax_details.append(file.relative_to(OUT).as_posix() + ": " + ("PASS" if result.returncode == 0 else result.stderr.strip()[:300]))
            syntax_pass = syntax_pass and result.returncode == 0
        checks.append({"check": "JavaScript syntax", "status": "PASS" if syntax_pass else "FAIL", "details": syntax_details})

        required = ["App.js", "app.json", "package.json", "src/screens/HomeScreen.js", "src/screens/AddTaskScreen.js", "src/screens/SettingsScreen.js", "src/components/TaskItem.js", "src/storage/taskStorage.js"]
        missing = [name for name in required if not (OUT / name).is_file()]
        checks.append({"check": "Project structure", "status": "PASS" if not missing else "FAIL", "details": {"missing": missing, "required_files": required}})

        dependency_map = {}
        dependency_error = None
        try:
            package = json.loads((OUT / "package.json").read_text(encoding="utf-8"))
            dependency_map = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
            needed = ["expo", "react", "react-native", "@react-native-async-storage/async-storage", "@react-navigation/native", "@react-navigation/native-stack"]
            missing_deps = [name for name in needed if name not in dependency_map]
        except Exception as exc:
            dependency_error = type(exc).__name__ + ": " + str(exc)
            needed, missing_deps = [], ["package.json"]
        checks.append({"check": "Dependency validation", "status": "PASS" if not missing_deps else "FAIL", "details": {"dependencies": {name: dependency_map.get(name) for name in needed}, "missing": missing_deps, "error": dependency_error}})

        try:
            config = json.loads((OUT / "app.json").read_text(encoding="utf-8")).get("expo", {})
            config_ok = bool(config.get("name") and config.get("slug") and config.get("version"))
            config_data = {key: config.get(key) for key in ("name", "slug", "version", "entryPoint")}
        except Exception as exc:
            config_ok = False
            config_data = {"error": type(exc).__name__ + ": " + str(exc)}
        checks.append({"check": "Expo configuration", "status": "PASS" if config_ok else "FAIL", "details": config_data})

        cli = OUT / "node_modules" / ".bin" / ("expo.cmd" if os.name == "nt" else "expo")
        if cli.exists():
            build = subprocess.run([str(cli), "prebuild", "--no-install", "--platform", "android"], cwd=OUT, capture_output=True, text=True, timeout=120)
            checks.append({"check": "Expo prebuild", "status": "PASS" if build.returncode == 0 else "FAIL", "details": (build.stdout + build.stderr)[-1000:]})
        else:
            checks.append({"check": "Expo prebuild", "status": "NOT_AVAILABLE", "details": "Expo packages are not installed locally; no package install or download was attempted."})
        self.results = checks
        return json.dumps({"status": "fail" if any(item["status"] == "FAIL" for item in checks) else "pass", "validation_results": checks}, ensure_ascii=False)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    report = {"model": MODEL, "requirement_status": "not_run", "architecture_status": "not_run", "developer_status": "not_run", "qa_build_status": "not_run", "agents_executed": [], "generated_files": [], "validation_results": [], "final_status": "fail", "errors": []}
    try:
        llm = get_default_llm()
        report["model"] = str(llm.model)
        if report["model"] != MODEL:
            raise RuntimeError("Configured model differs from required Gemini model; workflow not started")
        workflow = MobileWorkflow(llm=llm, max_iterations=1)
        for agent in workflow.agents.values():
            agent.verbose = False
            agent.cache = False
            agent.max_iter = 3
        workflow.agents["mobile_developer"].tools = [ScopedWriter()]
        validator = LocalValidationTool()
        workflow.agents["mobile_qa"].tools = [validator]
        crew = workflow.build_crew(REQUIREMENT)
        crew.tasks[0].description = "Extract concise requirements and acceptance criteria for this app: " + REQUIREMENT
        crew.tasks[1].description = "Define a compact Expo/React Native architecture for the supplied requirement. Use React Navigation native stack for Home, Add Task, Settings, and AsyncStorage for offline tasks. Keep it suitable for a small JavaScript Expo project."
        crew.tasks[2].description = (
            "Implement the mobile Todo app in output/live-mobile-demo only, using the supplied requirement and architecture. "
            "Write these small files through write_file using paths relative to output/: "
            "live-mobile-demo/package.json, live-mobile-demo/app.json, live-mobile-demo/App.js, "
            "live-mobile-demo/src/screens/HomeScreen.js, live-mobile-demo/src/screens/AddTaskScreen.js, "
            "live-mobile-demo/src/screens/SettingsScreen.js, live-mobile-demo/src/components/TaskItem.js, "
            "live-mobile-demo/src/storage/taskStorage.js. Include React Navigation and AsyncStorage dependencies, "
            "three navigable screens, add/complete/delete task flows, persistent local storage, and basic styling. "
            "Do not install packages, run commands, start an emulator, or write outside this directory."
        )
        crew.tasks[3].description = (
            "Call run_command exactly once with exact input `validate live mobile project`. "
            "This performs local JavaScript syntax, structure, declared dependency, Expo JSON configuration, "
            "and available no-install prebuild checks. Do not install/download anything, run another command, "
            "start an emulator, or deploy to app stores. Report only the tool's validation evidence."
        )
        crew.kickoff()
        labels = ["Mobile Requirement Agent", "Mobile Architecture Agent", "Mobile Developer Agent", "Mobile QA/Build Agent"]
        report["agents_executed"] = labels
        report["requirement_status"] = "pass"
        report["architecture_status"] = "pass"
        file_names = [path.relative_to(OUT).as_posix() for path in OUT.rglob("*") if path.is_file() and path.name not in ("mobile_report.json", "MOBILE_REPORT.md", "mobile_workflow_runner.py")]
        report["generated_files"] = sorted(file_names)
        source_files = ["App.js", "app.json", "package.json", "src/screens/HomeScreen.js", "src/screens/AddTaskScreen.js", "src/screens/SettingsScreen.js", "src/components/TaskItem.js", "src/storage/taskStorage.js"]
        report["developer_status"] = "pass" if all((OUT / name).is_file() for name in source_files) else "fail"
        report["validation_results"] = validator.results
        report["qa_build_status"] = "fail" if any(item["status"] == "FAIL" for item in validator.results) else "pass"
        if not validator.invoked:
            report["qa_build_status"] = "fail"
            report["errors"].append("Mobile QA/Build Agent did not invoke the configured validation tool.")
        report["final_status"] = "pass" if report["architecture_status"] == report["developer_status"] == report["qa_build_status"] == "pass" else "fail"
    except Exception as exc:
        message = str(exc)
        for key_name in ("TARGET_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
            secret = os.environ.get(key_name, "").strip()
            if secret:
                message = message.replace(secret, "[REDACTED]")
        message = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", message)
        report["errors"].append(type(exc).__name__ + ": " + message[:1000])
        report["generated_files"] = sorted(path.relative_to(OUT).as_posix() for path in OUT.rglob("*") if path.is_file() and path.name not in ("mobile_report.json", "MOBILE_REPORT.md", "mobile_workflow_runner.py"))
    write_json(OUT / "mobile_report.json", report)
    lines = ["# Mobile Workflow Report", "", f"- Model: `{report['model']}`", f"- Requirement status: **{report['requirement_status'].upper()}**", f"- Architecture status: **{report['architecture_status'].upper()}**", f"- Developer status: **{report['developer_status'].upper()}**", f"- QA/build status: **{report['qa_build_status'].upper()}**", f"- Final status: **{report['final_status'].upper()}**", "", "## Agents Executed"]
    lines.extend("- " + item for item in report["agents_executed"])
    lines.extend(["", "## Generated Files"])
    lines.extend("- " + item for item in report["generated_files"])
    lines.extend(["", "## Validation Results"])
    lines.extend("- " + item["check"] + ": **" + item["status"] + "**" for item in report["validation_results"])
    lines.extend(["", "## Errors"])
    lines.extend("- " + item for item in report["errors"] or ["None"])
    (OUT / "MOBILE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
