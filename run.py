"""Interactive CLI for the existing AI DevFlow workflows."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from workflows.mobile_workflow import MobileWorkflow
from workflows.web_workflow import WebWorkflow

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "output"


def _prompt_platform() -> str:
    while True:
        platform = input("Platform (web/mobile):\n> ").strip().lower()
        if platform in {"web", "mobile"}:
            return platform
        print("Enter 'web' or 'mobile'.")


def _project_directory(platform: str, requirement: str) -> Path:
    words = re.findall(r"[a-z0-9]+", requirement.lower())[:5]
    slug = "-".join(words) or "new-project"
    base = OUTPUT_ROOT / f"{platform}-{slug}"
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = base.with_name(f"{base.name}-{suffix}")
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def _run_demo(platform: str, requirement: str) -> int:
    workflow = MobileWorkflow() if platform == "mobile" else WebWorkflow()
    outcome = workflow.run_demo(requirement).run(requirement)
    print(f"Demo status: {'PASS' if outcome.passed else 'FAIL'}")
    print(f"Stages completed: {', '.join(outcome.state.completed_agents)}")
    return 0 if outcome.passed else 1


def _run_real(platform: str, requirement: str, project_dir: Path) -> int:
    from providers.llm_config import get_default_llm
    from schemas.project_results import StageStatus
    from supervisor import AutonomousSupervisor

    llm = get_default_llm()
    supervisor = AutonomousSupervisor(llm=llm, verbose=True)
    result = supervisor.run(
        requirement=requirement,
        platform=platform,
        project_dir=project_dir,
    )
    return 0 if result.status == StageStatus.PASS else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an existing AI DevFlow Web or Mobile workflow.")
    parser.add_argument("--demo", action="store_true", help="Run deterministic local stages without model/API calls.")
    args = parser.parse_args(argv)

    platform = _prompt_platform()
    requirement = input("Requirement:\n> ").strip()
    if not requirement:
        print("Requirement cannot be empty.", file=sys.stderr)
        return 2

    project_dir = _project_directory(platform, requirement)
    if args.demo:
        print(f"Demo output directory: {project_dir}")
        return _run_demo(platform, requirement)
    return _run_real(platform, requirement, project_dir)


if __name__ == "__main__":
    raise SystemExit(main())
