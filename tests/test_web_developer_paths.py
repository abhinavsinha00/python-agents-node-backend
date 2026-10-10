"""Local tests for safe Web Developer output path handling."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.file_tools import resolve_output_path
from workflows.web_workflow import WebWorkflow


class OutputPathTests(unittest.TestCase):
    def test_prefixed_output_path_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            self.assertEqual(
                resolve_output_path(
                    "output/web-build-a-test/index.html", output_root
                ),
                output_root / "web-build-a-test" / "index.html",
            )

    def test_output_relative_path_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            self.assertEqual(
                resolve_output_path("web-build-a-test/index.html", output_root),
                output_root / "web-build-a-test" / "index.html",
            )

    def test_rejects_absolute_and_traversal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            for unsafe_path in ("../outside.html", "C:/outside.html", "/outside.html"):
                with self.subTest(path=unsafe_path):
                    with self.assertRaises(ValueError):
                        resolve_output_path(unsafe_path, output_root)

    def test_postcondition_accepts_nonempty_required_project_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "output"
            project = output_root / "test-project"
            project.mkdir(parents=True)
            for filename in ("index.html", "style.css", "script.js"):
                (project / filename).write_text("content", encoding="utf-8")

            architecture = SimpleNamespace(
                output=SimpleNamespace(
                    raw=(
                        "Files: output/test-project/index.html, "
                        "test-project/style.css, script.js"
                    )
                )
            )
            developer = SimpleNamespace(
                description="Write generated files to output/test-project/."
            )
            with patch("workflows.web_workflow.PROJECT_DIR", output_root):
                WebWorkflow._validate_developer_files(
                    SimpleNamespace(raw="implementation summary"), architecture, developer
                )

    def test_postcondition_rejects_empty_required_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "output"
            project = output_root / "test-project"
            project.mkdir(parents=True)
            (project / "index.html").write_text("", encoding="utf-8")
            architecture = SimpleNamespace(
                output=SimpleNamespace(raw="Required file: test-project/index.html")
            )
            developer = SimpleNamespace(
                description="Write generated files to output/test-project/."
            )
            with patch("workflows.web_workflow.PROJECT_DIR", output_root):
                with self.assertRaisesRegex(RuntimeError, "missing or empty"):
                    WebWorkflow._validate_developer_files(
                        SimpleNamespace(raw="not actually written"), architecture, developer
                    )

    def test_valid_architecture_with_file_list(self) -> None:
        valid_arch = SimpleNamespace(
            raw=(
                "Architecture Plan: Web App\n"
                "Project Structure:\n"
                "- output/test-project/index.html\n"
                "- output/test-project/styles.css\n"
                "- output/test-project/script.js"
            )
        )
        self.assertTrue(WebWorkflow._validate_architecture_output(valid_arch))

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            project = output_root / "test-project"
            with patch("workflows.web_workflow.PROJECT_DIR", output_root):
                extracted = WebWorkflow._extract_required_files(
                    None, valid_arch, project
                )
                self.assertEqual(
                    extracted,
                    [Path("index.html"), Path("styles.css"), Path("script.js")],
                )

    def test_architecture_returning_identity_text(self) -> None:
        identity_arch = SimpleNamespace(
            raw="I am Gemini, a large language model trained by Google."
        )
        # Architecture validation detects identity text and returns False without crashing
        self.assertFalse(WebWorkflow._validate_architecture_output(identity_arch))

        # File extraction does not crash and falls back to deterministic web defaults
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            project = output_root / "test-project"
            with patch("workflows.web_workflow.PROJECT_DIR", output_root):
                extracted = WebWorkflow._extract_required_files(
                    None, identity_arch, project
                )
                self.assertEqual(
                    extracted,
                    [Path("index.html"), Path("styles.css"), Path("script.js")],
                )

    def test_architecture_returning_empty_text(self) -> None:
        empty_arch = SimpleNamespace(raw="   ")
        # Architecture validation returns False without crashing
        self.assertFalse(WebWorkflow._validate_architecture_output(empty_arch))
        self.assertFalse(WebWorkflow._validate_architecture_output(None))

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            project = output_root / "test-project"
            with patch("workflows.web_workflow.PROJECT_DIR", output_root):
                extracted = WebWorkflow._extract_required_files(
                    None, empty_arch, project
                )
                self.assertEqual(
                    extracted,
                    [Path("index.html"), Path("styles.css"), Path("script.js")],
                )

    def test_requirement_deliverables_used_successfully_when_architecture_is_malformed(self) -> None:
        from schemas.project_results import RequirementResult, RequirementStatus

        req_result = RequirementResult(
            status=RequirementStatus.PASS,
            summary="Tiny greeting website requirements.",
            scope="Web scope",
            deliverables=[
                "output/test-project/index.html",
                "output/test-project/styles.css",
                "output/test-project/script.js",
            ],
        )
        requirement_task = SimpleNamespace(
            output=SimpleNamespace(pydantic=req_result, raw=req_result.model_dump_json())
        )
        malformed_architecture = SimpleNamespace(
            output=SimpleNamespace(
                raw="I am Gemini, a large language model trained by Google."
            )
        )

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            project = output_root / "test-project"
            with patch("workflows.web_workflow.PROJECT_DIR", output_root):
                extracted = WebWorkflow._extract_required_files(
                    requirement_task, malformed_architecture, project
                )
                self.assertEqual(
                    extracted,
                    [Path("index.html"), Path("styles.css"), Path("script.js")],
                )

    def test_developer_postcondition_fails_when_files_are_missing(self) -> None:
        from schemas.project_results import RequirementResult, RequirementStatus

        req_result = RequirementResult(
            status=RequirementStatus.PASS,
            summary="Web requirements",
            scope="Web scope",
            deliverables=[
                "output/test-project/index.html",
                "output/test-project/styles.css",
                "output/test-project/script.js",
            ],
        )
        requirement_task = SimpleNamespace(
            output=SimpleNamespace(pydantic=req_result, raw=req_result.model_dump_json())
        )
        architecture_task = SimpleNamespace(
            output=SimpleNamespace(raw="I am Gemini, a large language model trained by Google.")
        )
        developer_task = SimpleNamespace(
            description="Write generated files to output/test-project/."
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "output"
            project = output_root / "test-project"
            project.mkdir(parents=True)
            # Create only index.html and styles.css; script.js is missing
            (project / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
            (project / "styles.css").write_text("body { color: black; }", encoding="utf-8")

            with patch("workflows.web_workflow.PROJECT_DIR", output_root):
                with self.assertRaisesRegex(RuntimeError, "script.js"):
                    WebWorkflow._validate_developer_files(
                        SimpleNamespace(raw="done"),
                        requirement_task=requirement_task,
                        architecture_task=architecture_task,
                        development_task=developer_task,
                    )

    def test_developer_postcondition_passes_when_all_required_files_exist(self) -> None:
        from schemas.project_results import RequirementResult, RequirementStatus

        req_result = RequirementResult(
            status=RequirementStatus.PASS,
            summary="Greeting website requirements",
            scope="Web scope",
            deliverables=[
                "output/test-project/index.html",
                "output/test-project/styles.css",
                "output/test-project/script.js",
            ],
        )
        requirement_task = SimpleNamespace(
            output=SimpleNamespace(pydantic=req_result, raw=req_result.model_dump_json())
        )
        architecture_task = SimpleNamespace(
            output=SimpleNamespace(raw="I am Gemini, a large language model trained by Google.")
        )
        developer_task = SimpleNamespace(
            description="Write generated files to output/test-project/."
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "output"
            project = output_root / "test-project"
            project.mkdir(parents=True)
            (project / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
            (project / "styles.css").write_text("body { color: black; }", encoding="utf-8")
            (project / "script.js").write_text("console.log('hi');", encoding="utf-8")

            with patch("workflows.web_workflow.PROJECT_DIR", output_root):
                # Validates without throwing any exception even though architecture was identity text
                WebWorkflow._validate_developer_files(
                    SimpleNamespace(raw="done"),
                    requirement_task=requirement_task,
                    architecture_task=architecture_task,
                    development_task=developer_task,
                )

    def test_greeting_workflow_proceeds_with_malformed_architecture(self) -> None:
        """Verify the greeting workflow proceeds Requirement -> Architecture -> Developer -> QA -> Code Review even if Architecture returns identity text."""
        from schemas.project_results import (
            CodeReviewResult,
            CodeReviewVerdict,
            QAResult,
            RequirementResult,
            RequirementStatus,
        )

        project_name = "web-build-a-tiny-greeting-website"
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            project_dir = output_root / project_name
            project_dir.mkdir(parents=True)

            with patch("workflows.web_workflow.PROJECT_DIR", output_root):
                # 1. Requirement Stage
                req_result = RequirementResult(
                    status=RequirementStatus.PASS,
                    summary="Build a tiny greeting website",
                    scope="Single-page greeting site",
                    technology_stack=["HTML", "CSS", "JavaScript"],
                    acceptance_criteria=["Displays greeting", "Interactive button"],
                    deliverables=[
                        f"output/{project_name}/index.html",
                        f"output/{project_name}/styles.css",
                        f"output/{project_name}/script.js",
                    ],
                )
                req_task = SimpleNamespace(
                    description=f"Convert this requirement into a bounded plan:\nbuild a tiny greeting website\nWrite all project files under output/{project_name}/.",
                    output=SimpleNamespace(pydantic=req_result, raw=req_result.model_dump_json()),
                )

                # 2. Architecture Stage (returns model identity text)
                arch_raw = "I am Gemini, a large language model trained by Google."
                arch_output = SimpleNamespace(raw=arch_raw)
                # Validation callback returns False but does NOT crash the workflow
                arch_valid = WebWorkflow._validate_architecture_output(arch_output)
                self.assertFalse(arch_valid)
                arch_task = SimpleNamespace(
                    description=f"Define the web architecture and project structure.\nUse output/{project_name}/ as the project root.",
                    output=arch_output,
                )

                # 3. Developer Stage (writes files and runs validation callback)
                (project_dir / "index.html").write_text("<!doctype html><h1>Hello World</h1>", encoding="utf-8")
                (project_dir / "styles.css").write_text("h1 { color: teal; }", encoding="utf-8")
                (project_dir / "script.js").write_text("console.log('Greeting ready');", encoding="utf-8")

                dev_task = SimpleNamespace(
                    description=f"Implement the approved architecture.\nWrite all generated files only under output/{project_name}/.",
                    output=SimpleNamespace(raw="Implemented greeting files successfully."),
                )
                # Developer validation callback uses Requirement deliverables as authoritative fallback
                WebWorkflow._validate_developer_files(
                    dev_task.output,
                    requirement_task=req_task,
                    architecture_task=arch_task,
                    development_task=dev_task,
                )

                # 4. QA Stage
                qa_task = SimpleNamespace(
                    output=SimpleNamespace(
                        pydantic=QAResult(status="pass", tests_run=3, passed=3, failed=0),
                        raw='{"status":"pass","tests_run":3,"passed":3,"failed":0}',
                    )
                )
                self.assertEqual(qa_task.output.pydantic.status, "pass")

                # 5. Code Review Stage
                review_task_output = SimpleNamespace(
                    raw=json.dumps({
                        "verdict": "PASS",
                        "findings": [],
                        "reviewed_files": [
                            f"output/{project_name}/index.html",
                            f"output/{project_name}/styles.css",
                            f"output/{project_name}/script.js",
                        ],
                        "summary": "Clean greeting website implementation.",
                    })
                )
                WebWorkflow._validate_review_output(review_task_output)
                self.assertEqual(review_task_output.pydantic.verdict, CodeReviewVerdict.PASS)


if __name__ == "__main__":
    unittest.main()
