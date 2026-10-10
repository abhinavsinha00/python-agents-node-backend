"""Central coordinator for deterministic Web and Mobile demo workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from schemas.project_results import (
    CodeReviewResult,
    CodeReviewVerdict,
    QAResult,
    RequirementResult,
    RequirementStatus,
)
from state.project_state import ProjectState

LOGGER = logging.getLogger(__name__)
StageRunner = Callable[[str, ProjectState], tuple[bool, Any]]


@dataclass
class WorkflowOutcome:
    state: ProjectState
    passed: bool
    result_type: str


class AgentWorkflowOrchestrator:
    """Run registered stages and keep execution state in one place."""

    def __init__(
        self,
        state: ProjectState,
        max_iterations: int = 3,
        stage_runner: StageRunner | dict[str, StageRunner] | None = None,
    ) -> None:
        self.state = state
        self.max_iterations = max(1, max_iterations)
        self.stage_runner = stage_runner

    def _log(self, message: str) -> None:
        self.state.log(message)
        LOGGER.info(message)

    def _run_stage(self, stage: str) -> Any:
        if self.stage_runner is None:
            raise RuntimeError(f"No stage runner configured for {stage}")
        runner = (
            self.stage_runner.get(stage)
            if isinstance(self.stage_runner, dict)
            else self.stage_runner
        )
        if runner is None:
            raise RuntimeError(f"No stage runner configured for {stage}")
        success, result = runner(stage, self.state)
        labels = {
            "requirement": "Requirement Agent",
            "architecture": "Architecture Agent",
            "developer": "Developer Agent",
            "qa": "QA/Test Agent",
            "review": "Code Review Agent",
            "bug_fix": "Bug Fix Agent",
            "deployment": "Deployment/Documentation Agent",
            "mobile_requirement": "Mobile Requirement Agent",
            "mobile_architecture": "Mobile Architecture Agent",
            "mobile_developer": "Mobile Developer Agent",
            "mobile_qa": "Mobile QA/Build Agent",
        }
        self.state.current_agent = labels[stage]
        self.state.completed_agents.append(labels[stage])
        return result if success else None

    def run(self, user_requirement: str) -> WorkflowOutcome:
        self.state.user_requirement = user_requirement
        self.state.iteration = 0
        self.state.completed_agents.clear()
        self.state.final_status = "running"
        self._log("Orchestrator started")

        if self.state.project_type == "mobile":
            return self._run_mobile()
        return self._run_web()

    def _run_mobile(self) -> WorkflowOutcome:
        stages = (
            "mobile_requirement",
            "mobile_architecture",
            "mobile_developer",
            "mobile_qa",
        )
        for stage in stages:
            self._log(f"{stage.replace('_', ' ').title()}: running")
            result = self._run_stage(stage)
            self.state.artifacts.append(stage)
            if stage == "mobile_requirement":
                self.state.requirement = result
            elif stage == "mobile_qa":
                self.state.qa_result = result
            if result is None:
                self.state.final_status = "failed"
                return WorkflowOutcome(self.state, False, stage)
        qa_result = self.state.qa_result
        self.state.final_status = (
            "passed" if qa_result is not None and qa_result.status == "pass" else "failed"
        )
        return WorkflowOutcome(self.state, self.state.final_status == "passed", "mobile")

    def _run_web(self) -> WorkflowOutcome:
        self.state.current_agent = "Requirement Agent"
        self._log("Requirement Agent: running")
        self.state.requirement = self._run_stage("requirement")
        if self.state.requirement is None:
            self.state.final_status = "failed"
            return WorkflowOutcome(self.state, False, "requirement")

        for stage in ("architecture", "developer"):
            self._log(f"{stage.title()} Agent: running")
            if self._run_stage(stage) is None:
                self.state.final_status = "failed"
                return WorkflowOutcome(self.state, False, stage)
            self.state.artifacts.append(stage)

        while self.state.iteration < self.max_iterations:
            self.state.iteration += 1
            self._log(f"QA/Test Agent: running (iteration {self.state.iteration})")
            self.state.qa_result = self._run_stage("qa")
            self._log("Code Review Agent: running")
            self.state.review_result = self._run_stage("review")
            if self.state.qa_result is None or self.state.review_result is None:
                break
            if (
                self.state.qa_result.status == "pass"
                and self.state.review_result.verdict == CodeReviewVerdict.PASS
            ):
                self._log("Deployment/Documentation Agent: running")
                if self._run_stage("deployment") is None:
                    self.state.final_status = "failed"
                    return WorkflowOutcome(self.state, False, "deployment")
                self.state.deployment_ready = True
                self.state.final_status = "passed"
                return WorkflowOutcome(self.state, True, "pass")
            self.state.failed_attempts += 1
            self._log("Bug Fix Agent: running")
            if self._run_stage("bug_fix") is None:
                break

        self.state.final_status = "failed"
        self._log("Workflow failed after iteration limit")
        return WorkflowOutcome(self.state, False, "failed")


def get_demo_stage_runner(project_type: str) -> dict[str, StageRunner]:
    """Return deterministic local results without constructing LLM agents."""

    mobile = project_type == "mobile"

    def requirement(_stage: str, _state: ProjectState) -> tuple[bool, Any]:
        return True, RequirementResult(
            status=RequirementStatus.PASS,
            summary=f"Deterministic {project_type} demo requirements.",
            features=["Core user workflow", "Local validation"],
            scope=f"Demo {project_type} scope",
            technology_stack=["React Native", "Expo"] if mobile else ["Python", "Flask"],
            acceptance_criteria=["All demo stages complete without external API calls."],
        )

    if mobile:
        return {
            "mobile_requirement": requirement,
            "mobile_architecture": lambda _stage, _state: (True, {"status": "pass", "platform": "Expo", "layers": ["Screens", "Components", "AsyncStorage"]}),
            "mobile_developer": lambda _stage, _state: (True, {"status": "pass", "scaffold": "React Native/Expo"}),
            "mobile_qa": lambda _stage, _state: (True, QAResult(status="pass", tests_run=3, passed=3, failed=0, build_status="pass", build_output="Local demo validation passed; no store deployment.")),
        }

    return {
        "requirement": requirement,
        "architecture": lambda _stage, _state: (True, {"status": "pass", "layers": ["UI", "API", "Services"]}),
        "developer": lambda _stage, _state: (True, {"status": "pass", "files": ["app.py", "tests.py"]}),
        "qa": lambda _stage, _state: (True, QAResult(status="pass", tests_run=4, passed=4, failed=0)),
        "review": lambda _stage, _state: (True, CodeReviewResult(verdict=CodeReviewVerdict.PASS, findings=[], reviewed_files=["app.py", "tests.py"], summary="Demo review passed.")),
        "bug_fix": lambda _stage, _state: (True, {"status": "pass", "repair": "No defects found."}),
        "deployment": lambda _stage, _state: (True, {"status": "pass", "documentation": "Local demo documentation ready."}),
    }


def run_demo_web() -> WorkflowOutcome:
    state = ProjectState(user_requirement="Demo web project", project_type="web")
    return AgentWorkflowOrchestrator(state, stage_runner=get_demo_stage_runner("web")).run(
        state.user_requirement
    )


def run_demo_mobile() -> WorkflowOutcome:
    state = ProjectState(user_requirement="Demo mobile project", project_type="mobile")
    return AgentWorkflowOrchestrator(state, stage_runner=get_demo_stage_runner("mobile")).run(
        state.user_requirement
    )