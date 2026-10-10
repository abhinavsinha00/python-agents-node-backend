"""Deterministic test suite for the autonomous Build -> Test -> Fix -> Deploy system."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from deployers.deployer import LocalStaticDeployer, sanitize_secrets
from schemas.project_results import (
    ArchitectureResult,
    CodeReviewVerdict,
    DeploymentResult,
    ExecutionResult,
    ImplementationResult,
    QAResult,
    RequirementResult,
    RequirementStatus,
    ReviewResult,
    StageFailure,
    StageStatus,
    TestCaseResult,
    TestResult,
)
from supervisor import AutonomousSupervisor
from tools.browser_test_tools import validate_web_application
from tools.file_tools import resolve_output_path
from tools.server_tools import ApplicationExecutor, LocalServerManager


class AutonomousSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_root = Path(self.temp_dir.name) / "output"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.patcher = patch("tools.file_tools.PROJECT_DIR", self.output_root)
        self.patcher2 = patch("supervisor.PROJECT_DIR", self.output_root)
        self.patcher.start()
        self.patcher2.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.patcher2.stop()
        self.temp_dir.cleanup()

    def _setup_working_greeting_files(self, project_dir: Path) -> None:
        (project_dir / "index.html").write_text(
            "<!DOCTYPE html><html><head><title>Greeting</title><link rel='stylesheet' href='styles.css'></head>"
            "<body><input type='text' id='nameInput'><button id='greetBtn'>Greet Me</button>"
            "<div id='greetingOutput'></div><script src='script.js'></script></body></html>",
            encoding="utf-8",
        )
        (project_dir / "styles.css").write_text("body { font-family: sans-serif; }", encoding="utf-8")
        (project_dir / "script.js").write_text(
            "document.getElementById('greetBtn').addEventListener('click', function() {"
            "  const name = document.getElementById('nameInput').value || 'World';"
            "  document.getElementById('greetingOutput').textContent = 'Hello, ' + name + '!';"
            "});",
            encoding="utf-8",
        )

    # 1. Normal build success
    def test_1_normal_build_success(self) -> None:
        project_dir = self.output_root / "test-project-1"
        project_dir.mkdir(parents=True)
        self._setup_working_greeting_files(project_dir)

        supervisor = AutonomousSupervisor(verbose=False)
        result = supervisor.run(
            requirement="Build a greeting website with name input and button.",
            platform="web",
            project_dir=project_dir,
            mock_stages={
                "requirement": RequirementResult(
                    status=RequirementStatus.PASS,
                    summary="Greeting website",
                    scope="Web app",
                    deliverables=["index.html", "styles.css", "script.js"],
                ),
            },
        )
        self.assertEqual(result.status, StageStatus.PASS)
        self.assertIsNotNone(result.final_url)
        self.assertTrue(result.final_url.startswith("http://127.0.0.1:"))
        self.assertEqual(result.fix_attempts, 0)
        self.assertEqual(result.qa_status, StageStatus.PASS)
        self.assertEqual(result.review_status, StageStatus.PASS)

    # 2. Missing developer files
    def test_2_missing_developer_files(self) -> None:
        project_dir = self.output_root / "test-project-2"
        project_dir.mkdir(parents=True)
        # Create only index.html, omit styles.css and script.js
        (project_dir / "index.html").write_text("<h1>Hi</h1>", encoding="utf-8")

        supervisor = AutonomousSupervisor(verbose=False)
        impl_res = supervisor._run_developer_stage(
            "Requirement",
            ArchitectureResult(),
            [Path("index.html"), Path("styles.css"), Path("script.js")],
            project_dir,
            mock_result=None,
        )
        self.assertEqual(impl_res.status, StageStatus.FAIL)
        self.assertIn("styles.css", impl_res.missing_files)
        self.assertIn("script.js", impl_res.missing_files)

    # 3. Empty developer file
    def test_3_empty_developer_file(self) -> None:
        project_dir = self.output_root / "test-project-3"
        project_dir.mkdir(parents=True)
        (project_dir / "index.html").write_text("", encoding="utf-8")  # Empty 0-byte file

        supervisor = AutonomousSupervisor(verbose=False)
        impl_res = supervisor._run_developer_stage(
            "Requirement",
            ArchitectureResult(),
            [Path("index.html")],
            project_dir,
            mock_result=None,
        )
        self.assertEqual(impl_res.status, StageStatus.FAIL)
        self.assertIn("index.html", impl_res.missing_files)

    # 4. Malformed architecture
    def test_4_malformed_architecture(self) -> None:
        project_dir = self.output_root / "test-project-4"
        project_dir.mkdir(parents=True)
        self._setup_working_greeting_files(project_dir)

        supervisor = AutonomousSupervisor(verbose=False)
        req = RequirementResult(
            status=RequirementStatus.PASS,
            summary="Web app",
            scope="Web scope",
            deliverables=["index.html", "styles.css", "script.js"],
        )
        arch, paths = supervisor._run_architecture_stage(
            "Build website", req, project_dir, mock_result="??? INVALID {MALFORMED} ARCHITECTURE ???"
        )
        # Does not crash, successfully resolves paths from requirement deliverables
        self.assertEqual([p.as_posix() for p in paths], ["index.html", "styles.css", "script.js"])

    # 5. Identity-text architecture
    def test_5_identity_text_architecture(self) -> None:
        project_dir = self.output_root / "test-project-5"
        project_dir.mkdir(parents=True)
        self._setup_working_greeting_files(project_dir)

        supervisor = AutonomousSupervisor(verbose=False)
        req = RequirementResult(
            status=RequirementStatus.PASS,
            summary="Web app",
            scope="Web scope",
            deliverables=["index.html", "styles.css", "script.js"],
        )
        arch, paths = supervisor._run_architecture_stage(
            "Build website", req, project_dir, mock_result="I am Gemini, a large language model trained by Google."
        )
        # Architecture validation detects identity text and falls back safely
        self.assertEqual([p.as_posix() for p in paths], ["index.html", "styles.css", "script.js"])

    # 6. Application startup failure
    def test_6_application_startup_failure(self) -> None:
        project_dir = self.output_root / "test-project-6"
        project_dir.mkdir(parents=True)
        self._setup_working_greeting_files(project_dir)
        exec_fail = ExecutionResult(
            status=StageStatus.FAIL,
            failure=StageFailure(error_type="PortConflict", message="Port already in use", stage="Execute"),
        )

        supervisor = AutonomousSupervisor(verbose=False)
        result = supervisor.run(
            requirement="Build app",
            platform="web",
            project_dir=project_dir,
            mock_stages={"execution": exec_fail},
        )
        self.assertEqual(result.status, StageStatus.FAIL)
        self.assertIsNone(result.final_url)

    # 7. Browser/test failure
    def test_7_browser_test_failure(self) -> None:
        project_dir = self.output_root / "test-project-7"
        project_dir.mkdir(parents=True)
        # Broken HTML without button or JS
        (project_dir / "index.html").write_text("<html><body>No buttons here</body></html>", encoding="utf-8")

        test_res = validate_web_application("http://127.0.0.1:8000/test-project-7/", project_dir, "name input and button")
        self.assertEqual(test_res.status, StageStatus.FAIL)
        self.assertIsNotNone(test_res.failure)

    # 8. Automatic fix succeeds on first attempt
    def test_8_automatic_fix_succeeds_on_first_attempt(self) -> None:
        project_dir = self.output_root / "test-project-8"
        project_dir.mkdir(parents=True)
        self._setup_working_greeting_files(project_dir)

        test_sequence = [
            TestResult(status=StageStatus.FAIL, failure=StageFailure(error_type="BtnFail", message="Button missing", stage="Test")),
            TestResult(status=StageStatus.PASS),
        ]
        supervisor = AutonomousSupervisor(verbose=False)
        result = supervisor.run(
            requirement="Build greeting site",
            platform="web",
            project_dir=project_dir,
            mock_stages={
                "test": lambda attempt: test_sequence[attempt],
                "fix": lambda attempt: ["script.js"],
            },
        )
        self.assertEqual(result.status, StageStatus.PASS)
        self.assertEqual(result.fix_attempts, 1)

    # 9. Automatic fix succeeds on second attempt
    def test_9_automatic_fix_succeeds_on_second_attempt(self) -> None:
        project_dir = self.output_root / "test-project-9"
        project_dir.mkdir(parents=True)
        self._setup_working_greeting_files(project_dir)

        test_sequence = [
            TestResult(status=StageStatus.FAIL, failure=StageFailure(error_type="Err1", message="Missing input", stage="Test")),
            TestResult(status=StageStatus.FAIL, failure=StageFailure(error_type="Err2", message="Wrong greeting format", stage="Test")),
            TestResult(status=StageStatus.PASS),
        ]
        supervisor = AutonomousSupervisor(verbose=False)
        result = supervisor.run(
            requirement="Build greeting site",
            platform="web",
            project_dir=project_dir,
            mock_stages={
                "test": lambda attempt: test_sequence[min(attempt, 2)],
                "fix": lambda attempt: ["script.js"],
            },
        )
        self.assertEqual(result.status, StageStatus.PASS)
        self.assertEqual(result.fix_attempts, 2)

    # 10. Repeated failure stops after MAX_FIX_ATTEMPTS
    def test_10_repeated_failure_stops_after_max_fix_attempts(self) -> None:
        project_dir = self.output_root / "test-project-10"
        project_dir.mkdir(parents=True)
        self._setup_working_greeting_files(project_dir)

        failing_test = TestResult(
            status=StageStatus.FAIL,
            failure=StageFailure(error_type="PersistentFailure", message="Permanent error", stage="Test"),
        )
        supervisor = AutonomousSupervisor(max_fix_attempts=5, verbose=False)
        result = supervisor.run(
            requirement="Build greeting site",
            platform="web",
            project_dir=project_dir,
            mock_stages={
                "test": lambda attempt: failing_test,
                "fix": lambda attempt: ["script.js"],
            },
        )
        self.assertEqual(result.status, StageStatus.FAIL)
        self.assertEqual(result.fix_attempts, 5)
        self.assertIsNone(result.final_url)  # No fabricated URL on failure

    # 11. Successful local deployment returns URL
    def test_11_successful_local_deployment_returns_url(self) -> None:
        project_dir = self.output_root / "test-project-11"
        project_dir.mkdir(parents=True)
        (project_dir / "index.html").write_text("<h1>Deployed</h1>", encoding="utf-8")

        deployer = LocalStaticDeployer()
        deploy_res = deployer.deploy(project_dir, "test-project-11")
        self.assertEqual(deploy_res.status, StageStatus.PASS)
        self.assertIsNotNone(deploy_res.url)
        self.assertIn("127.0.0.1", deploy_res.url)
        self.assertIn("test-project-11", deploy_res.url)

    # 12. Deployment failure does not fabricate URL
    def test_12_deployment_failure_does_not_fabricate_url(self) -> None:
        project_dir = self.output_root / "test-project-12"
        project_dir.mkdir(parents=True)
        self._setup_working_greeting_files(project_dir)

        failed_deploy = DeploymentResult(
            status=StageStatus.FAIL,
            url=None,
            failure=StageFailure(error_type="DeployError", message="Deployment failed", stage="Deploy"),
        )
        supervisor = AutonomousSupervisor(verbose=False)
        result = supervisor.run(
            requirement="Build greeting site",
            platform="web",
            project_dir=project_dir,
            mock_stages={"deploy": failed_deploy},
        )
        self.assertEqual(result.status, StageStatus.FAIL)
        self.assertIsNone(result.final_url)

    # 13. Final PASS requires real verification
    def test_13_final_pass_requires_real_verification(self) -> None:
        project_dir = self.output_root / "test-project-13"
        project_dir.mkdir(parents=True)
        # Do not create files; natural language alone claiming success must be rejected
        supervisor = AutonomousSupervisor(verbose=False)
        # Developer stage fails postcondition check
        impl_res = supervisor._run_developer_stage(
            "Requirement",
            ArchitectureResult(),
            [Path("index.html"), Path("styles.css"), Path("script.js")],
            project_dir,
            mock_result=None,
        )
        self.assertEqual(impl_res.status, StageStatus.FAIL)

    # 14. Secrets are not printed
    def test_14_secrets_are_not_printed(self) -> None:
        fake_secret = "secret-token-xyz-987654"
        with patch.dict(os.environ, {"TARGET_API_KEY": fake_secret}):
            raw_text = f"Error communicating with target api_key={fake_secret} and bearer {fake_secret}"
            sanitized = sanitize_secrets(raw_text)
            self.assertNotIn(fake_secret, sanitized)
            self.assertIn("[REDACTED]", sanitized)

    # 15. Greeting workflow end-to-end orchestration
    def test_15_greeting_workflow_end_to_end_orchestration(self) -> None:
        project_dir = self.output_root / "web-build-a-tiny-greeting-website"
        project_dir.mkdir(parents=True)
        self._setup_working_greeting_files(project_dir)

        supervisor = AutonomousSupervisor(verbose=False)
        result = supervisor.run(
            requirement="Build a tiny greeting website with a name input and a button. When clicked, display Hello, [name]!",
            platform="web",
            project_dir=project_dir,
        )
        self.assertEqual(result.status, StageStatus.PASS)
        self.assertIsNotNone(result.final_url)
        self.assertIn("web-build-a-tiny-greeting-website", result.final_url)
        self.assertEqual(result.qa_status, StageStatus.PASS)
        self.assertEqual(result.review_status, StageStatus.PASS)


if __name__ == "__main__":
    unittest.main()
