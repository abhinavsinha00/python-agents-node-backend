"""Run one bounded QA, review, and conditional fix/retest cycle."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crewai import Task
from pydantic import BaseModel, Field

from agents.web_agents import build_web_agents
from providers.llm_config import get_default_llm
from tools.file_tools import RunCommandTool, WriteFileTool


ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
MODEL = "gemini/gemini-3.5-flash-lite"


class QAResult(BaseModel):
    status: Literal["pass", "fail"]
    tests_passed: int = 0
    tests_failed: int = 0
    test_details: list[dict] = Field(default_factory=list)
    defects: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    cleanup_warnings: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    status: Literal["pass", "fail"]
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    summary: str
    reviewed_files: list[str] = Field(default_factory=list)


class FixResult(BaseModel):
    status: Literal["pass", "fail"]
    summary: str
    exact_fixes: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)


def write_json(name: str, value: dict) -> None:
    (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def result_data(output, schema):
    if output.pydantic is not None:
        return output.pydantic.model_dump()
    return schema.model_validate_json(output.raw).model_dump()


def redact(exc: Exception) -> str:
    message = str(exc)
    for variable in ("TARGET_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
        secret = os.environ.get(variable, "").strip()
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", message)
    return f"{type(exc).__name__}: {message[:500]}"


class SingleSuiteCommand(RunCommandTool):
    name: str = "run_command"
    description: str = "Run the deterministic six-check QA suite once. Exact input: run configured QA suite"
    called: bool = False
    evidence: dict | None = None

    def _run(self, command: str) -> str:
        if self.called or command.strip() != "run configured QA suite":
            return "ERROR: only one exact configured QA invocation is allowed"
        self.called = True
        run_id = uuid.uuid4().hex
        process = subprocess.run(
            [sys.executable, str(ROOT / "qa_runner.py"), run_id],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        lines = process.stdout.strip().splitlines()
        if process.returncode or not lines:
            self.evidence = {
                "status": "fail",
                "tests_passed": 0,
                "tests_failed": 6,
                "test_details": [{"name": "QA runner", "status": "FAIL", "evidence": (process.stderr or "No runner output")[:500]}],
                "defects": ["Deterministic QA runner failed to complete."],
                "recommendations": [],
                "cleanup_warnings": [],
            }
        else:
            self.evidence = json.loads(lines[-1])
        (ROOT / ".qa-last-run.json").write_text(
            json.dumps({"run_id": run_id, "result": self.evidence}, indent=2) + "\n",
            encoding="utf-8",
        )
        return json.dumps(self.evidence, ensure_ascii=False)


class AppOnlyWriter(WriteFileTool):
    name: str = "write_file"
    description: str = "Write only output/live-gemini-demo/app.py via path live-gemini-demo/app.py::content"

    def _run(self, tool_input: str) -> str:
        try:
            path, content = tool_input.split("::", 1)
        except ValueError:
            return "ERROR: expected path::content"
        target = (ROOT.parent / path.strip()).resolve()
        if target != APP.resolve():
            return "ERROR: only output/live-gemini-demo/app.py may be changed"
        target.write_text(content, encoding="utf-8")
        return "OK: wrote output/live-gemini-demo/app.py"


def main() -> dict:
    report = {
        "model": MODEL,
        "initial_qa": "not_run",
        "code_review": "not_run",
        "fix_agent_executed": False,
        "exact_fixes": [],
        "retest": "not_run",
        "final_status": "fail",
        "remaining_defects": [],
        "execution_error": None,
    }
    try:
        requirement = json.loads((ROOT / "requirements.json").read_text(encoding="utf-8"))
        architecture = json.loads((ROOT / "architecture.json").read_text(encoding="utf-8"))
        llm = get_default_llm()
        report["model"] = str(llm.model)
        if report["model"] != MODEL:
            raise RuntimeError("configured provider model is not the required Gemini model")
        agents = build_web_agents(llm)

        qa = agents["qa"]
        qa.verbose = False
        qa.cache = False
        qa.max_iter = 2
        first_tool = SingleSuiteCommand()
        qa.tools = [first_tool]
        qa_task = Task(
            description=(
                "Call run_command exactly once with exact input `run configured QA suite`. "
                "It runs six real Flask test-client/SQLite checks. Do not run other commands, "
                "edit files, start Flask, or delegate. Return evidence from the tool only.\n"
                + json.dumps({"requirements": requirement, "architecture": architecture}, ensure_ascii=False)
            ),
            expected_output="Structured QA JSON: status, counts, test_details, defects and recommendations.",
            agent=qa,
            output_pydantic=QAResult,
        )
        qa_output = qa_task.execute_sync()
        initial = result_data(qa_output, QAResult)
        if first_tool.evidence is None:
            initial = {
                "status": "fail", "tests_passed": 0, "tests_failed": 6,
                "test_details": [{"name": "QA invocation", "status": "FAIL", "evidence": "QA Agent did not call its configured test tool."}],
                "defects": ["QA Agent did not invoke its configured test tool."],
                "recommendations": [], "cleanup_warnings": [],
            }
        else:
            initial = first_tool.evidence
        write_json("qa_result_initial.json", initial)
        report["initial_qa"] = initial["status"]

        reviewer = agents["review"]
        reviewer.verbose = False
        reviewer.cache = False
        reviewer.max_iter = 2
        review_task = Task(
            description=(
                "Review only app.py for correctness, security, maintainability, Flask practices, "
                "SQLite connection closure, CSRF, POST-only mutations, error handling, and code quality. "
                "Mark fail only for concrete remaining defects. Do not edit files or run commands.\nAPP:\n"
                + APP.read_text(encoding="utf-8")
                + "\nINITIAL QA:\n"
                + json.dumps(initial, ensure_ascii=False)
            ),
            expected_output="Structured review JSON with status, findings, recommendations, summary and reviewed_files.",
            agent=reviewer,
            context=[qa_task],
            output_pydantic=ReviewResult,
        )
        review_output = review_task.execute_sync()
        review = result_data(review_output, ReviewResult)
        write_json("code_review.json", review)
        report["code_review"] = review["status"]

        if initial["status"] != "pass" or review["status"] != "pass":
            report["fix_agent_executed"] = True
            fixer = agents["bug_fix"]
            fixer.role = "Fix Agent"
            fixer.verbose = False
            fixer.cache = False
            fixer.max_iter = 3
            fixer.tools = [AppOnlyWriter()]
            fix_task = Task(
                description=(
                    "Apply only concrete QA/review defects to output/live-gemini-demo/app.py. "
                    "Make minimal changes, preserve all features, do not run commands, and do not "
                    "change any other file. Use write_file only for path live-gemini-demo/app.py.\n"
                    + json.dumps({"qa": initial, "review": review}, ensure_ascii=False)
                    + "\nAPP:\n"
                    + APP.read_text(encoding="utf-8")
                ),
                expected_output="Structured JSON with status, summary, exact_fixes and files_changed.",
                agent=fixer,
                context=[qa_task, review_task],
                output_pydantic=FixResult,
            )
            fix_output = fix_task.execute_sync()
            fix = result_data(fix_output, FixResult)
            write_json("fix_result.json", fix)
            report["exact_fixes"] = fix.get("exact_fixes") or [fix.get("summary", "")]

            retest_tool = SingleSuiteCommand()
            qa.tools = [retest_tool]
            retest_task = Task(
                description="Call run_command exactly once with exact input `run configured QA suite` to retest. Do not run other commands, edit files, start Flask, or delegate.",
                expected_output="Structured QA JSON with test details and defects.",
                agent=qa,
                output_pydantic=QAResult,
            )
            retest_output = retest_task.execute_sync()
            retest = result_data(retest_output, QAResult)
            if retest_tool.evidence is None:
                retest = {
                    "status": "fail", "tests_passed": 0, "tests_failed": 6,
                    "test_details": [{"name": "QA retest invocation", "status": "FAIL", "evidence": "QA Agent did not call its configured test tool."}],
                    "defects": ["QA Agent did not invoke its configured retest tool."],
                    "recommendations": [], "cleanup_warnings": [],
                }
            else:
                retest = retest_tool.evidence
            write_json("qa_result_retest.json", retest)
            report["retest"] = retest["status"]
            report["remaining_defects"] = retest.get("defects", [])
            report["final_status"] = "pass" if retest["status"] == "pass" else "fail"
        else:
            report["final_status"] = "pass"
    except Exception as exc:
        report["execution_error"] = redact(exc)
        report["remaining_defects"].append(report["execution_error"])
        report["final_status"] = "fail"

    write_json("final_report.json", report)
    lines = [
        "# Final Quality Report", "",
        f"- Model: `{report['model']}`",
        f"- Initial QA result: **{report['initial_qa'].upper()}**",
        f"- Code review result: **{report['code_review'].upper()}**",
        f"- Fix Agent executed: **{'Yes' if report['fix_agent_executed'] else 'No'}**",
        "- Exact fixes: " + ("; ".join(report["exact_fixes"]) if report["exact_fixes"] else "None"),
        f"- Retest result: **{report['retest'].upper()}**",
        f"- Final result: **{report['final_status'].upper()}**",
        "- Remaining defects: " + ("; ".join(report["remaining_defects"]) if report["remaining_defects"] else "None"),
    ]
    if report["execution_error"]:
        lines.extend(["", "Execution error: " + report["execution_error"]])
    (ROOT / "FINAL_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()