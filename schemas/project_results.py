"""Pydantic models for structured workflow results and autonomous supervisor state."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RequirementStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class RequirementResult(BaseModel):
    """Structured output produced by the Requirement Agent."""

    status: RequirementStatus
    summary: str
    features: list[str] = Field(default_factory=list)
    scope: str
    technology_stack: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)


class QAResult(BaseModel):
    """Structured test and build evidence produced by the QA Agent."""

    status: Literal["pass", "fail"]
    tests_run: int = 0
    passed: int = 0
    failed: int = 0
    failures: list[str] = Field(default_factory=list)
    build_status: Literal["not_run", "pass", "fail"] = "not_run"
    build_output: str = ""


class CodeReviewVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class CodeReviewResult(BaseModel):
    """Structured review output produced by the Code Review Agent."""

    verdict: CodeReviewVerdict
    findings: list[str] = Field(default_factory=list)
    reviewed_files: list[str] = Field(default_factory=list)
    summary: str


class StageStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    RETRY = "RETRY"


class StageFailure(BaseModel):
    """Structured failure representation for any lifecycle stage."""

    error_type: str
    message: str
    stage: str
    affected_files: list[str] = Field(default_factory=list)
    evidence: str = ""
    suggested_action: str = ""


class ArchitectureResult(BaseModel):
    """Structured output for the architecture stage."""

    status: StageStatus = StageStatus.PASS
    summary: str = ""
    components: list[str] = Field(default_factory=list)
    required_files: list[str] = Field(default_factory=list)
    raw_output: str = ""


class ImplementationResult(BaseModel):
    """Result of developer code generation and filesystem inspection."""

    status: StageStatus = StageStatus.PASS
    written_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    summary: str = ""
    failure: StageFailure | None = None


class ExecutionResult(BaseModel):
    """Runtime execution result of starting the application."""

    status: StageStatus = StageStatus.PASS
    app_type: Literal["static", "backend"] = "static"
    running_url: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    failure: StageFailure | None = None


class TestCaseResult(BaseModel):
    """Individual test check outcome."""

    name: str
    passed: bool
    message: str = ""


class TestResult(BaseModel):
    """Comprehensive test outcome from web validation or unit tests."""

    status: StageStatus = StageStatus.PASS
    tests_run: int = 0
    passed: int = 0
    failed: int = 0
    details: list[TestCaseResult] = Field(default_factory=list)
    console_errors: list[str] = Field(default_factory=list)
    broken_assets: list[str] = Field(default_factory=list)
    failure: StageFailure | None = None


class RepairAttempt(BaseModel):
    """Log record of an individual repair cycle."""

    attempt_number: int
    error: str
    diagnosis: str
    files_changed: list[str] = Field(default_factory=list)
    test_result: TestResult | None = None


class FixResult(BaseModel):
    """Structured outcome produced by the Fixer / Bug Fix Agent."""

    status: StageStatus = StageStatus.PASS
    attempt_number: int = 1
    root_cause: str = ""
    files_modified: list[str] = Field(default_factory=list)
    explanation: str = ""
    failure: StageFailure | None = None


class ReviewResult(BaseModel):
    """Structured code review result."""

    status: StageStatus = StageStatus.PASS
    verdict: CodeReviewVerdict = CodeReviewVerdict.PASS
    findings: list[str] = Field(default_factory=list)
    reviewed_files: list[str] = Field(default_factory=list)
    summary: str = ""
    failure: StageFailure | None = None


class DeploymentResult(BaseModel):
    """Structured output for local or cloud application deployment."""

    status: StageStatus = StageStatus.PASS
    url: str | None = None
    deployment_type: Literal["local", "cloud"] = "local"
    summary: str = ""
    failure: StageFailure | None = None


class BuildState(BaseModel):
    """Single unified build state maintained by the autonomous supervisor."""

    project_id: str
    platform: str = "web"
    project_dir: str
    requirement: str
    required_files: list[str] = Field(default_factory=list)
    architecture: ArchitectureResult | None = None
    implementation_status: StageStatus = StageStatus.RETRY
    running_url: str | None = None
    execution_result: ExecutionResult | None = None
    test_result: TestResult | None = None
    repair_attempts: list[RepairAttempt] = Field(default_factory=list)
    qa_result: QAResult | None = None
    review_result: ReviewResult | None = None
    deployment_result: DeploymentResult | None = None
    final_url: str | None = None
    overall_status: StageStatus = StageStatus.RETRY


class BuildRunResult(BaseModel):
    """Final outcome returned by the autonomous supervisor."""

    project_id: str
    platform: str
    status: StageStatus
    final_url: str | None = None
    fix_attempts: int = 0
    qa_status: StageStatus = StageStatus.PASS
    review_status: StageStatus = StageStatus.PASS
    state: BuildState
    message: str = ""
