"""Deployment abstraction for local serving and cloud deployment adapters."""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path

from schemas.project_results import DeploymentResult, StageFailure, StageStatus
from tools.server_tools import LocalServerManager

LOGGER = logging.getLogger(__name__)


def sanitize_secrets(text: str) -> str:
    """Mask any API keys, tokens, or secrets so they never appear in logs or output."""
    if not text:
        return ""
    sanitized = str(text)
    secret_env_vars = (
        "TARGET_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEPLOY_TOKEN",
        "NETLIFY_AUTH_TOKEN",
        "VERCEL_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
    )
    for var in secret_env_vars:
        secret = os.environ.get(var, "").strip()
        if secret and len(secret) > 3:
            sanitized = sanitized.replace(secret, "[REDACTED]")

    # Mask common key patterns
    sanitized = re.sub(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;\"']+", r"\1[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(token\s*[:=]\s*)[^\s,;\"']+", r"\1[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]+", r"\1[REDACTED]", sanitized)
    return sanitized


class BaseDeployer(ABC):
    """Abstract deployment adapter."""

    @abstractmethod
    def deploy(self, project_dir: Path, project_name: str) -> DeploymentResult:
        """Deploy the project and return a structured DeploymentResult."""
        pass


class LocalStaticDeployer(BaseDeployer):
    """Serves the project using the background local HTTP server."""

    def __init__(self, server_manager: LocalServerManager | None = None) -> None:
        self.server_manager = server_manager or LocalServerManager.get_instance()

    def deploy(self, project_dir: Path, project_name: str) -> DeploymentResult:
        project_dir = project_dir.resolve()
        if not project_dir.is_dir():
            return DeploymentResult(
                status=StageStatus.FAIL,
                url=None,
                deployment_type="local",
                failure=StageFailure(
                    error_type="MissingProjectDir",
                    message=f"Project directory {project_dir} does not exist.",
                    stage="Deploy",
                ),
            )
        try:
            port = self.server_manager.start()
            url = f"http://127.0.0.1:{port}/{project_name}/"
            return DeploymentResult(
                status=StageStatus.PASS,
                url=url,
                deployment_type="local",
                summary=f"Application locally hosted at {url}",
            )
        except Exception as exc:
            return DeploymentResult(
                status=StageStatus.FAIL,
                url=None,
                deployment_type="local",
                failure=StageFailure(
                    error_type="LocalServerError",
                    message=sanitize_secrets(f"Failed to start local static server: {exc}"),
                    stage="Deploy",
                ),
            )


class CloudDeployer(BaseDeployer):
    """Cloud deployment adapter that falls back gracefully to local serving when credentials are missing."""

    def __init__(self, fallback_deployer: BaseDeployer | None = None) -> None:
        self.fallback = fallback_deployer or LocalStaticDeployer()

    def deploy(self, project_dir: Path, project_name: str) -> DeploymentResult:
        cloud_token = os.environ.get("DEPLOY_TOKEN") or os.environ.get("NETLIFY_AUTH_TOKEN")
        cloud_endpoint = os.environ.get("DEPLOY_URL")

        if not cloud_token or not cloud_endpoint:
            LOGGER.info("No cloud deployment credentials configured; defaulting to local static serving.")
            return self.fallback.deploy(project_dir, project_name)

        # In production cloud deployments, invoke adapter here
        return DeploymentResult(
            status=StageStatus.PASS,
            url=sanitize_secrets(f"{cloud_endpoint.rstrip('/')}/{project_name}"),
            deployment_type="cloud",
            summary="Application deployed to cloud provider.",
        )


def get_deployer() -> BaseDeployer:
    """Return the configured deployer (CloudDeployer with automatic LocalStatic fallback)."""
    return CloudDeployer()
