"""Opt-in command-line entry point for the real Web CrewAI workflow."""

from __future__ import annotations

from workflows.web_workflow import WebWorkflow


def main() -> None:
    requirement = input("Describe your website/app idea: ").strip()
    if not requirement:
        raise SystemExit("A project requirement is required.")
    result = WebWorkflow().build_crew(requirement).kickoff()
    print(result)


if __name__ == "__main__":
    main()