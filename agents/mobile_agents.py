"""Agent factories for the mobile development workflow."""

from typing import Any

from crewai import Agent

from providers.llm_config import get_default_llm
from tools.agent_tools import WriteJsonResultTool
from tools.file_tools import RunCommandTool, WriteFileTool


def _llm() -> Any:
    return get_default_llm()


def build_mobile_agents(llm: Any | None = None):
    """Create mobile architecture, implementation, and validation agents."""
    llm = llm or _llm()
    return {
        "mobile_requirement": Agent(
            role="Mobile Requirement Agent",
            goal="Turn the mobile request into concise features and acceptance criteria.",
            backstory="You are a mobile product analyst. Define the requested mobile scope without designing architecture or writing code.",
            llm=llm,
            verbose=True,
        ),
        "mobile_architecture": Agent(
            role="Mobile Architecture Agent",
            goal="Define the Expo/React Native architecture and platform constraints.",
            backstory="You are a mobile platform architect. Define native boundaries, app structure, and validation targets without writing app code.",
            llm=llm,
            verbose=True,
        ),
        "mobile_developer": Agent(
            role="Mobile Developer Agent",
            goal="Scaffold and implement the mobile application with Expo-compatible code.",
            backstory="You are a mobile engineer. Generate React Native/Expo project files and keep platform-specific code isolated.",
            llm=llm,
            verbose=True,
            tools=[WriteFileTool(), WriteJsonResultTool()],
        ),
        "mobile_qa": Agent(
            role="Mobile QA/Build Agent",
            goal="Validate the mobile application and run build checks without store deployment.",
            backstory="You are a mobile QA engineer. Run lint, type checks, tests, and package/build validation. Never deploy to App Store or Play Store.",
            llm=llm,
            verbose=True,
            tools=[RunCommandTool(), WriteJsonResultTool()],
        ),
    }
