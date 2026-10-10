"""Central, serializable state shared by the orchestrator and agents."""

from dataclasses import dataclass, field
from typing import Optional

from schemas.project_results import CodeReviewResult, QAResult, RequirementResult


@dataclass
class ProjectState:
    """Mutable workflow state used by the central orchestrator."""

    user_requirement: str
    project_type: str = "web"
    iteration: int = 0
    current_agent: Optional[str] = None
    completed_agents: list[str] = field(default_factory=list)
    final_status: str = "pending"
    requirement: Optional[RequirementResult] = None
    qa_result: Optional[QAResult] = None
    review_result: Optional[CodeReviewResult] = None
    artifacts: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    failed_attempts: int = 0
    deployment_ready: bool = False

    def log(self, message: str) -> None:
        self.logs.append(message)

