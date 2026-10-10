"""Non-interactive JSON bridge from the Node API to the existing agent workflows."""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = (PROJECT_ROOT / "output").resolve()
MAX_REQUIREMENT_LENGTH = 8_000


def _sanitize(text: Any) -> str:
    value = str(text)
    for name in (
        "TARGET_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEPLOY_TOKEN",
        "NETLIFY_AUTH_TOKEN",
        "VERCEL_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
    ):
        secret = os.environ.get(name, "").strip()
        if len(secret) > 3:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;\"']+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(token\s*[:=]\s*)[^\s,;\"']+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(bearer\s+)[a-zA-Z0-9_.-]+", r"\1[REDACTED]", value)
    return value


def _progress(stage: str, percent: int, message: str) -> None:
    event = {"stage": stage, "percent": percent, "message": message}
    print("AGENT_PROGRESS " + json.dumps(event), file=sys.stderr, flush=True)


def _generated_files(project_dir: Path) -> list[str]:
    files = []
    for path in project_dir.rglob("*"):
        if path.is_file():
            resolved = path.resolve()
            if resolved.is_relative_to(project_dir):
                files.append(resolved.relative_to(project_dir).as_posix())
    return sorted(files)


def _status_value(status: Any) -> str:
    return str(getattr(status, "value", status)).strip().lower()


def _required_output_paths(result: Any, project_id: str) -> list[Path]:
    state = getattr(result, "state", None)
    required_files = getattr(state, "required_files", None) or (
        "index.html",
        "styles.css",
        "script.js",
    )
    paths = []
    for raw_path in required_files:
        value = str(raw_path).strip().replace("\\", "/")
        windows_path = PureWindowsPath(value)
        relative_path = PurePosixPath(value)
        if windows_path.is_absolute() or windows_path.drive or relative_path.is_absolute():
            raise ValueError("Supervisor returned an absolute required output path")
        parts = [part for part in relative_path.parts if part not in {"", "."}]
        if any(part == ".." for part in parts):
            raise ValueError("Supervisor returned a required path outside the project")
        while parts and parts[0].lower() == "output":
            parts.pop(0)
        if parts and parts[0] == project_id:
            parts.pop(0)
        if not parts:
            raise ValueError("Supervisor returned an empty required output path")
        paths.append(Path(*parts))
    return paths


def _missing_required_files(result: Any, project_id: str, project_dir: Path) -> list[str]:
    missing = []
    for relative_path in _required_output_paths(result, project_id):
        target = (project_dir / relative_path).resolve()
        if not target.is_relative_to(project_dir) or not target.is_file() or target.stat().st_size == 0:
            missing.append(relative_path.as_posix())
    return missing


def _url_is_reachable(url: str) -> bool:
    try:
        with urlopen(url, timeout=1) as response:
            return 200 <= response.status < 400
    except (OSError, URLError, ValueError):
        return False


def _failure_result(
    job_id: str,
    project_id: str,
    platform: str,
    project_dir: Path,
    message: str,
    error_type: str = "BuildFailed",
) -> dict[str, Any]:
    return {
        "jobId": job_id,
        "projectId": project_id,
        "platform": platform,
        "status": "failed",
        "projectPath": str(project_dir),
        "generatedFiles": _generated_files(project_dir),
        "finalUrl": None,
        "message": "Agent workflow failed.",
        "error": {"type": error_type, "message": _sanitize(message)[:2_000]},
    }


def _run_web(
    requirement: str,
    project_id: str,
    project_dir: Path,
    job_id: str,
    llm_factory=None,
    supervisor_factory=None,
) -> dict[str, Any]:
    if llm_factory is None:
        from providers.llm_config import get_default_llm

        llm_factory = get_default_llm
    if supervisor_factory is None:
        from supervisor import AutonomousSupervisor

        supervisor_factory = AutonomousSupervisor

    _progress("web", 5, "Starting Web agent workflow")
    llm = llm_factory()
    supervisor = supervisor_factory(llm=llm, verbose=True, project_dir=project_dir)
    result = supervisor.run(
        requirement=requirement,
        platform="web",
        project_dir=project_dir,
    )
    state = getattr(result, "state", None)
    succeeded = (
        _status_value(getattr(result, "status", None)) == "pass"
        and _status_value(getattr(state, "overall_status", None)) == "pass"
    )
    files = _generated_files(project_dir)
    if not succeeded:
        return _failure_result(
            job_id,
            project_id,
            "web",
            project_dir,
            getattr(result, "message", "Web supervisor reported failure."),
        )
    missing_files = _missing_required_files(result, project_id, project_dir)
    if missing_files:
        return _failure_result(
            job_id,
            project_id,
            "web",
            project_dir,
            "Web supervisor reported success but required output files are missing or empty: "
            + ", ".join(missing_files),
            "MissingRequiredFiles",
        )
    final_url = getattr(result, "final_url", None)
    if final_url:
        try:
            parsed_url = urlsplit(final_url)
            if (
                parsed_url.scheme not in {"http", "https"}
                or not parsed_url.hostname
                or parsed_url.username
                or parsed_url.password
                or not _url_is_reachable(final_url)
            ):
                final_url = None
        except ValueError:
            final_url = None
        if final_url:
            final_url = _sanitize(final_url)
    return {
        "jobId": job_id,
        "projectId": project_id,
        "platform": "web",
        "status": "succeeded",
        "projectPath": str(project_dir),
        "generatedFiles": files,
        "finalUrl": final_url or None,
        "message": _sanitize(getattr(result, "message", "Web build completed."))[:500],
        "error": None,
    }


def _run_mobile(
    requirement: str,
    project_id: str,
    project_dir: Path,
    job_id: str,
    llm_factory=None,
    mobile_workflow_factory=None,
) -> dict[str, Any]:
    if llm_factory is None:
        from providers.llm_config import get_default_llm

        llm_factory = get_default_llm
    if mobile_workflow_factory is None:
        from workflows.mobile_workflow import MobileWorkflow

        mobile_workflow_factory = MobileWorkflow

    _progress("mobile", 5, "Starting Mobile CrewAI workflow")
    llm = llm_factory()
    workflow = mobile_workflow_factory(llm=llm, project_dir=project_dir)
    for agent in workflow.agents.values():
        agent.verbose = False
        agent.cache = False
        agent.max_iter = 3

    crew = workflow.build_crew(requirement)
    task_stages = ("Mobile requirements", "Mobile architecture", "Mobile development", "Mobile QA")
    for index, task in enumerate(crew.tasks):
        stage = task_stages[min(index, len(task_stages) - 1)]

        def on_task_complete(_output, stage_name=stage, task_index=index):
            _progress(stage_name, min(90, 15 + (task_index + 1) * 18), stage_name + " completed")

        task.callback = on_task_complete

    crew.verbose = False
    _progress("mobile", 10, "Executing four Mobile CrewAI tasks")
    crew.kickoff()
    files = _generated_files(project_dir)
    if not files:
        return _failure_result(
            job_id,
            project_id,
            "mobile",
            project_dir,
            "Mobile CrewAI tasks completed without generating project files.",
            "NoGeneratedFiles",
        )

    qa_output = ""
    if crew.tasks and getattr(crew.tasks[-1], "output", None) is not None:
        qa_output = str(getattr(crew.tasks[-1].output, "raw", "")).strip()
    try:
        qa_result = json.loads(qa_output)
    except json.JSONDecodeError:
        qa_result = None
    qa_status = qa_result.get("status", "").lower() if isinstance(qa_result, dict) else ""
    if qa_status not in {"pass", "fail"}:
        return _failure_result(
            job_id,
            project_id,
            "mobile",
            project_dir,
            "Mobile QA task did not return a valid JSON pass/fail status.",
            "InvalidMobileQAResult",
        )
    if qa_status == "fail":
        return _failure_result(
            job_id,
            project_id,
            "mobile",
            project_dir,
            "Mobile QA task reported failure: " + _sanitize(qa_result.get("summary", "QA checks failed"))[:1_000],
            "MobileQAFailed",
        )

    return {
        "jobId": job_id,
        "projectId": project_id,
        "platform": "mobile",
        "status": "succeeded",
        "projectPath": str(project_dir),
        "generatedFiles": files,
        "finalUrl": None,
        "message": "Mobile CrewAI workflow completed and generated project files.",
        "error": None,
    }


def run_build(
    payload: dict[str, Any],
    *,
    repository_root: Path = PROJECT_ROOT,
    llm_factory=None,
    supervisor_factory=None,
    mobile_workflow_factory=None,
) -> dict[str, Any]:
    platform = payload.get("platform")
    requirement = payload.get("requirement")
    job_id = payload.get("jobId")
    if not isinstance(platform, str) or platform not in {"web", "mobile"}:
        raise ValueError("platform must be 'web' or 'mobile'")
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError("requirement must be a non-empty string")
    requirement = requirement.strip()
    if len(requirement) > MAX_REQUIREMENT_LENGTH:
        raise ValueError(f"requirement must be at most {MAX_REQUIREMENT_LENGTH} characters")
    try:
        parsed_id = uuid.UUID(str(job_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("jobId must be a UUID") from exc
    if str(parsed_id) != str(job_id).lower():
        raise ValueError("jobId must be a canonical UUID")

    project_id = f"{platform}-{parsed_id}"
    output_root = (Path(repository_root).resolve() / "output").resolve()
    project_dir = (output_root / project_id).resolve()
    if not project_dir.is_relative_to(output_root) or project_dir == output_root:
        raise ValueError("resolved project path is outside output/")
    output_root.mkdir(parents=True, exist_ok=True)
    project_dir.mkdir(parents=False, exist_ok=False)

    if platform == "web":
        return _run_web(
            requirement,
            project_id,
            project_dir,
            str(parsed_id),
            llm_factory,
            supervisor_factory,
        )
    return _run_mobile(
        requirement,
        project_id,
        project_dir,
        str(parsed_id),
        llm_factory,
        mobile_workflow_factory,
    )


def main() -> int:
    payload = None
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        with contextlib.redirect_stdout(sys.stderr):
            result = run_build(payload)
        exit_code = 0 if result["status"] == "succeeded" else 1
    except Exception as exc:
        job_id = ""
        platform = ""
        project_id = ""
        project_path = None
        files = []
        if isinstance(payload, dict):
            requested_platform = payload.get("platform")
            platform = (
                requested_platform
                if isinstance(requested_platform, str) and requested_platform in {"web", "mobile"}
                else ""
            )
            try:
                parsed_id = uuid.UUID(str(payload.get("jobId", "")))
                if str(parsed_id) == str(payload.get("jobId", "")).lower() and platform:
                    job_id = str(parsed_id)
                    project_id = f"{platform}-{parsed_id}"
                    candidate = (OUTPUT_ROOT / project_id).resolve()
                    if candidate.is_relative_to(OUTPUT_ROOT) and candidate.is_dir():
                        project_path = str(candidate)
                        files = _generated_files(candidate)
            except (ValueError, TypeError, AttributeError):
                pass
        result = {
            "jobId": job_id,
            "projectId": project_id,
            "platform": platform,
            "status": "failed",
            "projectPath": project_path,
            "generatedFiles": files,
            "finalUrl": None,
            "message": "Python agent bridge failed.",
            "error": {"type": type(exc).__name__, "message": _sanitize(exc)[:2_000]},
        }
        exit_code = 1
    sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    sys.stdout.flush()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())