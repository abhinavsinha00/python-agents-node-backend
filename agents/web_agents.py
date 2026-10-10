"""Agent factories for the web development workflow."""

from pathlib import Path
from typing import Any

from crewai import Agent

from providers.llm_config import get_default_llm
from tools.agent_tools import WriteJsonResultTool
from tools.file_tools import RunCommandTool, WriteFileTool


def _llm() -> Any:
    return get_default_llm()


def build_web_agents(
    llm: Any | None = None,
    output_dir: Path | None = None,
    project_id: str | None = None,
):
    """Create clearly separated web agents with limited responsibilities."""
    llm = llm or _llm()
    return {
        "requirement": Agent(
            role="Requirement Agent",
            goal="Turn the user requirement into a bounded feature and acceptance plan.",
            backstory="You are a product analyst. Produce requirements only; do not write code.",
            llm=llm,
            verbose=True,
        ),
        "architecture": Agent(
            role="Architecture Agent",
            goal="Select an implementation architecture and project structure.",
            backstory="You are a software architect. Define layers, interfaces, and file layout; do not implement code.",
            llm=llm,
            verbose=True,
        ),
        "developer": Agent(
            role="Developer Agent",
            goal="Implement the approved web requirement and architecture.",
            backstory="You are a web developer. Generate code and save it through the existing write_file tool only.",
            llm=llm,
            verbose=True,
            tools=[WriteFileTool(output_dir=output_dir, project_id=project_id), WriteJsonResultTool(output_dir=output_dir, project_id=project_id)],
        ),
        "qa": Agent(
            role="QA/Test Agent",
            goal="Run tests, validate behavior, and report structured evidence.",
            backstory="You are a QA engineer. Run project checks and return strict pass/fail results.",
            llm=llm,
            verbose=True,
            tools=[RunCommandTool(output_dir=output_dir), WriteJsonResultTool(output_dir=output_dir, project_id=project_id)],
        ),
        "review": Agent(
            role="Code Review Agent",
            goal="Review code quality, correctness, security, and test coverage.",
            backstory="You are a senior reviewer. Return only a structured verdict and findings.",
            llm=llm,
            verbose=True,
        ),
        "bug_fix": Agent(
            role="Bug Fix Agent",
            goal="Repair only findings returned by the Code Review Agent.",
            backstory="You are a bug-fix engineer. Apply the reported defects and rerun relevant checks.",
            llm=llm,
            verbose=True,
            tools=[WriteFileTool(output_dir=output_dir, project_id=project_id), RunCommandTool(output_dir=output_dir)],
        ),
        "deployment": Agent(
            role="Deployment/Documentation Agent",
            goal="Document setup, validation, deployment, and operational behavior.",
            backstory="You are a DevOps and documentation engineer. Produce documentation and deployment instructions, not deployment to external services.",
            llm=llm,
            verbose=True,
            tools=[WriteFileTool(output_dir=output_dir, project_id=project_id), WriteJsonResultTool(output_dir=output_dir, project_id=project_id)],
        ),
    }
