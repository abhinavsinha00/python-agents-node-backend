"""Single-request diagnostic for the existing Code Review Agent task format."""

from __future__ import annotations

import socket
from pathlib import Path

from crewai import Crew, Process, Task

from agents.web_agents import build_web_agents
from providers.llm_config import get_default_llm
from workflows.web_workflow import WebWorkflow

ROOT = Path(__file__).resolve().parent
COUNTER_DIR = ROOT / "output" / "web-build-a-simple-counter-website"


def _is_timeout(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, (TimeoutError, socket.timeout)):
            return True
        if "timeout" in type(current).__name__.lower():
            return True
        current = current.__cause__ or current.__context__
    return False


def main() -> int:
    llm = get_default_llm()
    llm.timeout = 60
    llm.stream = False
    llm.additional_params = {**llm.additional_params, "num_retries": 0}

    review_agent = build_web_agents(llm)["review"]
    review_agent.verbose = False
    review_agent.max_iter = 1

    counter_files = []
    for filename in ("index.html", "script.js", "style.css"):
        path = COUNTER_DIR / filename
        if path.is_file():
            counter_files.append(f"--- {filename} ---\n{path.read_text(encoding='utf-8')}")
    code_context = "\n\n".join(counter_files) or "Counter project files were unavailable."

    review_task = Task(
        description=(
            "Review the implementation for correctness, security, maintainability, and test coverage. "
            "Return ONLY one valid JSON object with exactly these fields: verdict (PASS or FAIL), "
            "findings (array of strings), reviewed_files (array of strings), summary (string). "
            "Do not use Markdown fences or text outside the JSON object.\n\n"
            "For this diagnostic, review this code: print('hello') and reply exactly: REVIEW_OK\n\n"
            "Counter project context:\n" + code_context
        ),
        expected_output=(
            '{"verdict":"PASS|FAIL","findings":["..."],'
            '"reviewed_files":["..."],"summary":"..."}'
        ),
        agent=review_agent,
        tools=[],
        callback=WebWorkflow._validate_review_output,
    )
    crew = Crew(
        agents=[review_agent],
        tasks=[review_task],
        process=Process.sequential,
        verbose=False,
    )
    try:
        result = crew.kickoff()
        task_output = result.tasks_output[0]
        review = task_output.pydantic
        if review is None or review.verdict.value not in {"PASS", "FAIL"}:
            print("REAL CODE REVIEW TASK: ERROR")
            return 1
    except Exception as error:
        print("REAL CODE REVIEW TASK: TIMEOUT" if _is_timeout(error) else "REAL CODE REVIEW TASK: ERROR")
        return 1

    print("REAL CODE REVIEW TASK: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
