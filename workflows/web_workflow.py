"""Web development workflow using the shared CrewAI agent factories."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from crewai import Crew, Process, Task
from pydantic import ValidationError

from agents.web_agents import build_web_agents
from orchestrator import AgentWorkflowOrchestrator, get_demo_stage_runner
from schemas.project_results import CodeReviewResult, CodeReviewVerdict
from state.project_state import ProjectState
from tools.file_tools import PROJECT_DIR, resolve_output_path

LOGGER = logging.getLogger(__name__)

DEFAULT_WEB_FILES = ["index.html", "styles.css", "script.js"]


def _resolve_candidate_file(candidate: str, project_root: Path, project_name: str) -> Path | None:
    candidate_clean = candidate.strip().strip("'\"`")
    if not candidate_clean:
        return None
    normalized_candidate = candidate_clean.replace("\\", "/")
    candidate_parts = [p for p in normalized_candidate.split("/") if p]
    if not candidate_parts:
        return None
    while candidate_parts and candidate_parts[0].lower() == "output":
        candidate_parts.pop(0)
    if not candidate_parts:
        return None

    try:
        if candidate_parts[0] == project_name:
            rel_candidate = "/".join(candidate_parts)
        else:
            rel_candidate = f"{project_name}/{'/'.join(candidate_parts)}"
        output_dir = project_root.parent if project_root.parent != project_root else PROJECT_DIR
        try:
            resolved = resolve_output_path(rel_candidate, PROJECT_DIR)
            if not resolved.is_relative_to(project_root):
                resolved = resolve_output_path(rel_candidate, output_dir)
        except ValueError:
            resolved = resolve_output_path(rel_candidate, output_dir)
    except ValueError:
        return None

    if resolved == project_root or not resolved.is_relative_to(project_root):
        return None
    return resolved.relative_to(project_root)


def _extract_deliverables_from_requirement(requirement_output: Any) -> list[str]:
    """Extract structured deliverables list from Requirement Agent output."""
    if requirement_output is None:
        return []

    target = getattr(requirement_output, "output", requirement_output)
    if target is None:
        return []

    # 1. Pydantic model
    pyd = getattr(target, "pydantic", None)
    if pyd is not None and hasattr(pyd, "deliverables") and pyd.deliverables:
        return [str(d) for d in pyd.deliverables if d]
    if hasattr(target, "deliverables") and target.deliverables:
        return [str(d) for d in target.deliverables if d]

    # 2. json_dict
    jdict = getattr(target, "json_dict", None)
    if isinstance(jdict, dict) and jdict.get("deliverables"):
        deliv = jdict["deliverables"]
        if isinstance(deliv, list):
            return [str(d) for d in deliv if d]

    # 3. Dict directly
    if isinstance(target, dict) and target.get("deliverables"):
        deliv = target["deliverables"]
        if isinstance(deliv, list):
            return [str(d) for d in deliv if d]

    # 4. Raw text / string
    raw_text = (
        target.raw
        if hasattr(target, "raw") and isinstance(target.raw, str)
        else (target if isinstance(target, str) else "")
    )
    if raw_text and raw_text.strip():
        # Direct JSON parse
        try:
            parsed = json.loads(raw_text.strip())
            if isinstance(parsed, dict) and parsed.get("deliverables"):
                deliv = parsed["deliverables"]
                if isinstance(deliv, list):
                    return [str(d) for d in deliv if d]
        except (json.JSONDecodeError, ValueError):
            pass

        # Code block JSON parse
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        if fence_match:
            try:
                parsed = json.loads(fence_match.group(1))
                if isinstance(parsed, dict) and parsed.get("deliverables"):
                    deliv = parsed["deliverables"]
                    if isinstance(deliv, list):
                        return [str(d) for d in deliv if d]
            except (json.JSONDecodeError, ValueError):
                pass

        # Regex search for deliverables array in text
        match = re.search(r'"deliverables"\s*:\s*\[(.*?)\]', raw_text, re.DOTALL)
        if match:
            found_items = re.findall(r'"([^"]+)"', match.group(1))
            if found_items:
                return found_items

    return []


def _extract_files_from_architecture(architecture_output: Any) -> list[str]:
    """Extract file paths from Architecture Agent output."""
    if architecture_output is None:
        return []

    target = getattr(architecture_output, "output", architecture_output)
    if target is None:
        return []

    # 1. Pydantic model
    pyd = getattr(target, "pydantic", None)
    for attr in ("files", "required_files", "deliverables"):
        val = getattr(pyd, attr, None) if pyd else None
        if isinstance(val, list) and val:
            return [str(v) for v in val if v]

    # 2. json_dict
    jdict = getattr(target, "json_dict", None)
    if isinstance(jdict, dict):
        for key in ("files", "required_files", "deliverables"):
            val = jdict.get(key)
            if isinstance(val, list) and val:
                return [str(v) for v in val if v]

    # 3. Dict directly
    if isinstance(target, dict):
        for key in ("files", "required_files", "deliverables"):
            val = target.get(key)
            if isinstance(val, list) and val:
                return [str(v) for v in val if v]

    # 4. Raw text / string
    raw_text = (
        target.raw
        if hasattr(target, "raw") and isinstance(target.raw, str)
        else (target if isinstance(target, str) else "")
    )
    if raw_text and raw_text.strip():
        # Try JSON parse
        try:
            parsed = json.loads(raw_text.strip())
            if isinstance(parsed, dict):
                for key in ("files", "required_files", "deliverables"):
                    val = parsed.get(key)
                    if isinstance(val, list) and val:
                        return [str(v) for v in val if v]
        except (json.JSONDecodeError, ValueError):
            pass

        # Check candidate files in text
        candidates = re.findall(
            r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_.-]+[\\/])*"
            r"[A-Za-z0-9_.-]+\.(?:html?|css|js|mjs|cjs|py|json|ya?ml|toml|sql|md|svg)",
            raw_text,
            flags=re.IGNORECASE,
        )
        if candidates:
            return candidates

    return []


def _extract_required_files(
    requirement_output: Any,
    architecture_output: Any,
    project_dir: Path | str,
) -> list[Path]:
    """Extract required files with priority:
    a) structured Requirement Agent deliverables
    b) structured Architecture Agent file list
    c) deterministic web defaults ONLY if neither output provides paths:
       index.html
       styles.css
       script.js
    """
    if isinstance(project_dir, Path):
        project_root = project_dir.resolve()
        project_name = project_dir.name
    else:
        normalized = str(project_dir).strip().replace("\\", "/")
        parts = [p for p in normalized.split("/") if p and p.lower() != "output"]
        project_name = parts[-1] if parts else "project"
        project_root = (PROJECT_DIR / project_name).resolve()

    # Priority a: structured Requirement Agent deliverables
    req_deliverables = _extract_deliverables_from_requirement(requirement_output)
    resolved_req_files: list[Path] = []
    for item in req_deliverables:
        resolved = _resolve_candidate_file(item, project_root, project_name)
        if resolved is not None and resolved not in resolved_req_files:
            resolved_req_files.append(resolved)
    if resolved_req_files:
        return resolved_req_files

    # Priority b: structured Architecture Agent file list
    arch_files = _extract_files_from_architecture(architecture_output)
    resolved_arch_files: list[Path] = []
    for item in arch_files:
        resolved = _resolve_candidate_file(item, project_root, project_name)
        if resolved is not None and resolved not in resolved_arch_files:
            resolved_arch_files.append(resolved)
    if resolved_arch_files:
        return resolved_arch_files

    # Priority c: deterministic web defaults
    default_files: list[Path] = []
    for default_name in DEFAULT_WEB_FILES:
        resolved = _resolve_candidate_file(default_name, project_root, project_name)
        if resolved is not None and resolved not in default_files:
            default_files.append(resolved)
    return default_files


_ACTIVE_CREW_TASKS: dict[str, Any] = {}


def validate_developer_task_callback(output: Any) -> None:
    """Module-level named callback to safely validate Developer files without lambda serialization warnings."""
    WebWorkflow._validate_developer_files(
        output,
        architecture_task=_ACTIVE_CREW_TASKS.get("architecture"),
        development_task=_ACTIVE_CREW_TASKS.get("developer"),
        requirement_task=_ACTIVE_CREW_TASKS.get("requirement"),
    )


class WebWorkflow:
    """Builds and runs the web agent workflow without executing it automatically."""

    _extract_required_files = staticmethod(_extract_required_files)

    def __init__(self, llm=None, max_iterations: int = 3) -> None:
        self.agents = build_web_agents(llm)
        self.max_iterations = max_iterations

    def build_crew(self, user_requirement: str) -> Crew:
        requirement_task = Task(
            description=(
                f"Convert this requirement into a bounded plan:\n{user_requirement}\n"
                "Include a structured deliverables list containing the required file paths "
                "(e.g., index.html, styles.css, script.js)."
            ),
            expected_output="RequirementResult JSON matching the requirement schema, including deliverables.",
            agent=self.agents["requirement"],
        )
        architecture_task = Task(
            description=(
                "Define the web architecture and project structure from the approved requirements.\n"
                "Do not respond with model identity, capabilities, or conversational filler.\n"
                "Return the architecture and project structure.\n"
                "Include a machine-readable list of required files.\n"
                "The expected web files are index.html, styles.css, script.js when applicable."
            ),
            expected_output=(
                "Architecture summary and project structure with a machine-readable list of required files "
                "(index.html, styles.css, script.js when applicable)."
            ),
            agent=self.agents["architecture"],
            context=[requirement_task],
            callback=self._validate_architecture_output,
        )
        development_task = Task(
            description=(
                "Implement the approved architecture and create every required project file. "
                "Use the write_file tool for every file. Do not answer with an explanation before writing files. "
                "Do not respond with model identity, capabilities, or unrelated text. "
                "The task is not complete until all required files physically exist and are non-empty. "
                "After writing, verify the required files exist. Return a concise implementation summary only "
                "after successful file creation.\n"
                "write_file accepts paths relative to the output directory; never prefix paths with output/.\n\n"
                "For this task, a final natural-language answer without file creation is a FAILURE. "
                "You must use write_file to create the required project files.\n"
                "Do not discuss your identity.\n"
                "Do not explain what you would do.\n"
                "Actually perform the file writes."
            ),
            expected_output="Concise implementation summary after all required files have been written and verified.",
            agent=self.agents["developer"],
            context=[requirement_task, architecture_task],
            callback=validate_developer_task_callback,
        )
        _ACTIVE_CREW_TASKS["requirement"] = requirement_task
        _ACTIVE_CREW_TASKS["architecture"] = architecture_task
        _ACTIVE_CREW_TASKS["developer"] = development_task
        qa_task = Task(
            description="Run the web tests, build checks, and produce structured QA results.",
            expected_output="QAResult JSON.",
            agent=self.agents["qa"],
            context=[development_task],
        )
        review_task = Task(
            description=(
                "Review the implementation for correctness, security, maintainability, and test coverage. "
                "Return ONLY one valid JSON object with exactly these fields: verdict (PASS or FAIL), "
                "findings (array of strings), reviewed_files (array of strings), summary (string). "
                "Do not use Markdown fences or text outside the JSON object."
            ),
            expected_output=(
                '{"verdict":"PASS|FAIL","findings":["..."],'
                '"reviewed_files":["..."],"summary":"..."}'
            ),
            agent=self.agents["review"],
            context=[development_task, qa_task],
            callback=self._validate_review_output,
        )
        return Crew(
            agents=list(self.agents.values()),
            tasks=[requirement_task, architecture_task, development_task, qa_task, review_task],
            process=Process.sequential,
            verbose=True,
        )

    @staticmethod
    def _validate_architecture_output(task_output) -> bool:
        """Validate architecture output separately without crashing the workflow.

        Detects whether architecture output is valid or malformed/identity/empty text.
        Returns True if valid architecture, False if malformed, identity text, or empty.
        """
        if task_output is None:
            return False

        raw_text = (
            task_output.raw
            if hasattr(task_output, "raw") and isinstance(task_output.raw, str)
            else (task_output if isinstance(task_output, str) else "")
        )
        trimmed = raw_text.strip()
        if not trimmed:
            return False

        identity_patterns = [
            r"\bi am (?:gemini|chatgpt|claude|an? ai|a large language model)\b",
            r"\bas an ai (?:language model|assistant)\b",
            r"\bi'm (?:gemini|chatgpt|claude|an? ai|a large language model)\b",
            r"\bi am a language model\b",
        ]
        is_identity = any(
            re.search(pat, trimmed, flags=re.IGNORECASE) for pat in identity_patterns
        )

        has_files = bool(
            re.search(
                r"[A-Za-z0-9_.-]+\.(?:html?|css|js|mjs|cjs|py|json|ya?ml|toml|sql|md|svg)",
                trimmed,
                flags=re.IGNORECASE,
            )
        )
        has_architecture_keywords = bool(
            re.search(
                r"\b(architecture|structure|components?|layers?|frontend|backend|modules?|layout)\b",
                trimmed,
                flags=re.IGNORECASE,
            )
        )

        if is_identity and not has_files and not has_architecture_keywords:
            return False

        if not has_files and not has_architecture_keywords:
            return False

        return True

    @classmethod
    def _validate_developer_files(
        cls,
        task_output,
        *args,
        architecture_task=None,
        development_task=None,
        requirement_task=None,
    ) -> None:
        """Stop the sequential crew if required files were not written."""
        if len(args) == 2:
            arg0, arg1 = args
            if hasattr(arg1, "description") and re.search(r"\boutput[\\/]([A-Za-z0-9_.-]+)[\\/]", arg1.description):
                development_task = arg1
                architecture_task = arg0
            elif hasattr(arg0, "description") and re.search(r"\boutput[\\/]([A-Za-z0-9_.-]+)[\\/]", arg0.description):
                development_task = arg0
                architecture_task = arg1
            else:
                architecture_task = arg0
                development_task = arg1
        elif len(args) >= 3:
            arg0, arg1, arg2 = args[0], args[1], args[2]
            if hasattr(arg2, "description") and re.search(r"\boutput[\\/]([A-Za-z0-9_.-]+)[\\/]", arg2.description):
                development_task = arg2
                requirement_task = arg0
                architecture_task = arg1
            elif hasattr(arg1, "description") and re.search(r"\boutput[\\/]([A-Za-z0-9_.-]+)[\\/]", arg1.description):
                development_task = arg1
                architecture_task = arg0
                requirement_task = arg2
            else:
                requirement_task = arg0
                architecture_task = arg1
                development_task = arg2

        dev_desc = getattr(development_task, "description", "") or ""
        path_match = re.search(r"\boutput[\\/]([A-Za-z0-9_.-]+)[\\/]", dev_desc)
        if path_match is None:
            raise RuntimeError("Developer stage FAIL: project output directory was not specified.")
        project_name = path_match.group(1)
        project_root = (PROJECT_DIR / project_name).resolve()
        if not project_root.is_relative_to(PROJECT_DIR):
            raise RuntimeError("Developer stage FAIL: invalid project output directory.")

        required_files = cls._extract_required_files(
            requirement_task, architecture_task, project_root
        )

        missing_or_empty = [
            str(project_root / relative_path)
            for relative_path in required_files
            if not (project_root / relative_path).is_file()
            or (project_root / relative_path).stat().st_size == 0
        ]
        if missing_or_empty:
            missing = ", ".join(missing_or_empty)
            raise RuntimeError(f"Developer stage FAIL: required files missing or empty: {missing}")

    @staticmethod
    def _validate_review_output(task_output):
        """Validate review JSON locally without requesting a model retry."""
        try:
            parsed = json.loads(task_output.raw)
            review = CodeReviewResult.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            review = CodeReviewResult(
                verdict=CodeReviewVerdict.FAIL,
                findings=[f"Code Review output was invalid JSON or schema: {type(exc).__name__}"],
                reviewed_files=[],
                summary="Review failed local JSON/schema validation; no retry was attempted.",
            )
        task_output.raw = review.model_dump_json()
        task_output.pydantic = review
        task_output.json_dict = review.model_dump(mode="json")
        return None

    def run_demo(self, requirement: str | None = None) -> AgentWorkflowOrchestrator:
        """Run only the deterministic demo flow; no LLM or external API call occurs."""
        state = ProjectState(
            user_requirement=requirement or "Demo web project",
            project_type="web",
        )
        return AgentWorkflowOrchestrator(
            state,
            self.max_iterations,
            stage_runner=get_demo_stage_runner("web"),
        )

    def run(self, user_requirement: str) -> AgentWorkflowOrchestrator:
        """Prepare a stateful workflow; execution is intentionally opt-in."""
        state = ProjectState(user_requirement=user_requirement, project_type="web")
        return AgentWorkflowOrchestrator(state, self.max_iterations)
