"""Mobile development workflow using Expo/React Native architecture and validation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from crewai import Crew, Process, Task
from pydantic import BaseModel

from agents.mobile_agents import build_mobile_agents
from orchestrator import AgentWorkflowOrchestrator, get_demo_stage_runner
from state.project_state import ProjectState


def _normalize_mobile_task_result(result: object) -> str:
    """Convert CrewAI mobile task results to TaskOutput's required string form."""
    if isinstance(result, str):
        return result
    if isinstance(result, BaseModel):
        return result.model_dump_json()
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        messages = []
        for item in result:
            if isinstance(item, BaseModel):
                item = item.model_dump(mode="json")
            if isinstance(item, dict):
                message = item.get("message", item)
                if isinstance(message, dict):
                    content = message.get("content")
                    calls = message.get("tool_calls") or message.get("toolCalls") or []
                    if content:
                        messages.append(str(content))
                    if calls:
                        names = [
                            call.get("function", {}).get("name", "tool")
                            if isinstance(call, dict)
                            else str(call)
                            for call in calls
                        ]
                        messages.append("Tool calls: " + ", ".join(names))
                    if not content and not calls:
                        messages.append(json.dumps(message, ensure_ascii=False, default=str))
                else:
                    messages.append(str(message))
            else:
                content = getattr(item, "content", None)
                calls = getattr(item, "tool_calls", None)
                if content:
                    messages.append(str(content))
                if calls:
                    messages.append("Tool calls: " + ", ".join(str(call) for call in calls))
                if not content and not calls:
                    messages.append(str(item))
        return "\n".join(messages) or "Mobile agent completed with structured message output."
    return str(result)


class MobileWorkflow:
    """Builds the mobile workflow and keeps store deployment out of scope."""

    def __init__(
        self,
        llm=None,
        max_iterations: int = 3,
        project_dir: Path | None = None,
    ) -> None:
        self.project_dir = project_dir.resolve() if project_dir is not None else None
        project_id = self.project_dir.name if self.project_dir is not None else None
        self.agents = build_mobile_agents(
            llm,
            output_dir=self.project_dir,
            project_id=project_id,
        )
        self.max_iterations = max_iterations
        developer = self.agents["mobile_developer"]
        original_execute_task = developer.execute_task

        def execute_task_with_string_result(task, context=None, tools=None) -> str:
            result = original_execute_task(task, context=context, tools=tools)
            return _normalize_mobile_task_result(result)

        object.__setattr__(
            developer,
            "execute_task",
            execute_task_with_string_result,
        )

    def build_crew(self, user_requirement: str) -> Crew:
        requirement_task = Task(
            description=f"Define concise mobile requirements and acceptance criteria for:\n{user_requirement}",
            expected_output="Mobile features, screens, offline behavior, and acceptance criteria.",
            agent=self.agents["mobile_requirement"],
        )
        architecture_task = Task(
            description=f"Define the Expo/React Native architecture for:\n{user_requirement}",
            expected_output="Mobile architecture and platform constraints.",
            agent=self.agents["mobile_architecture"],
            context=[requirement_task],
        )
        development_task = Task(
            description=(
                "Scaffold and implement the mobile application with local validation checks."
                + (
                    f" Write every generated file only inside output/{self.project_dir.name}/."
                    if self.project_dir is not None
                    else ""
                )
            ),
            expected_output="Mobile source files and build summary.",
            agent=self.agents["mobile_developer"],
            context=[requirement_task, architecture_task],
        )
        qa_task = Task(
            description=(
                "Run mobile unit tests, lint/type checks, and a local package/build check. "
                "Do not deploy to app stores."
                + (
                    ' Return exactly one JSON object with status "pass" or "fail", a summary, and a failures array.'
                    if self.project_dir is not None
                    else ""
                )
            ),
            expected_output=(
                '{"status":"pass|fail","summary":"...","failures":[]}'
                if self.project_dir is not None
                else "Mobile QA and build results."
            ),
            agent=self.agents["mobile_qa"],
            context=[development_task],
        )
        return Crew(
            agents=list(self.agents.values()),
            tasks=[requirement_task, architecture_task, development_task, qa_task],
            process=Process.sequential,
            verbose=True,
        )

    def run_demo(self, requirement: str | None = None) -> AgentWorkflowOrchestrator:
        """Run the deterministic mobile workflow structure without LLM calls."""
        state = ProjectState(
            user_requirement=requirement or "Demo mobile project",
            project_type="mobile",
        )
        return AgentWorkflowOrchestrator(
            state,
            self.max_iterations,
            stage_runner=get_demo_stage_runner("mobile"),
        )

    def run(self, user_requirement: str) -> AgentWorkflowOrchestrator:
        """Prepare a stateful workflow; execution is opt-in and API-free only in demo mode."""
        state = ProjectState(user_requirement=user_requirement, project_type="mobile")
        return AgentWorkflowOrchestrator(state, self.max_iterations)
