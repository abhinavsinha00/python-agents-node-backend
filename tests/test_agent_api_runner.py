"""Offline tests for the non-interactive API bridge and scoped output tools."""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from agent_api_runner import run_build
from tools.agent_tools import WriteJsonResultTool
from tools.file_tools import WriteFileTool


class FakeSupervisor:
    def __init__(self, llm, verbose, project_dir, status="PASS"):
        self.project_dir = project_dir
        self.status = status

    def run(self, requirement, platform, project_dir):
        assert project_dir == self.project_dir
        (project_dir / "index.html").write_text("<h1>test</h1>", encoding="utf-8")
        return SimpleNamespace(
            status=self.status,
            project_id=project_dir.name,
            final_url="http://127.0.0.1:8000/test/" if self.status == "PASS" else None,
            message="Web workflow completed" if self.status == "PASS" else "Web execution failed",
        )


class FakeCrew:
    def __init__(self, project_dir, qa_output='{"status":"pass","summary":"QA passed","failures":[]}'):
        self.project_dir = project_dir
        self.verbose = True
        self.tasks = [SimpleNamespace(output=None, callback=None) for _ in range(4)]
        self.tasks[-1].output = SimpleNamespace(raw=qa_output)

    def kickoff(self):
        (self.project_dir / "App.js").write_text("export default function App() {}", encoding="utf-8")
        for task in self.tasks:
            if task.callback:
                task.callback(SimpleNamespace())


class FakeMobileWorkflow:
    def __init__(self, llm, project_dir, qa_output='{"status":"pass","summary":"QA passed","failures":[]}'):
        self.project_dir = project_dir
        self.agents = {name: SimpleNamespace(verbose=True, cache=True, max_iter=99) for name in ("req", "arch", "dev", "qa")}
        self.crew = FakeCrew(project_dir, qa_output)

    def build_crew(self, requirement):
        return self.crew


class AgentApiRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "output").mkdir()
        self.job_id = str(uuid.uuid4())

    def tearDown(self):
        self.temp_dir.cleanup()

    def payload(self, platform="web", **overrides):
        return {"jobId": self.job_id, "platform": platform, "requirement": "Build a small app", **overrides}

    def test_rejects_invalid_platform_requirement_and_job_id(self):
        for payload in (
            self.payload(platform="tablet"),
            self.payload(platform=[]),
            self.payload(requirement="  "),
            self.payload(requirement="x" * 8001),
            self.payload(jobId="..\\outside"),
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    run_build(payload, repository_root=self.root)

    def test_web_dispatch_uses_supervisor_and_returns_real_result_fields(self):
        result = run_build(
            self.payload("web"),
            repository_root=self.root,
            llm_factory=lambda: object(),
            supervisor_factory=FakeSupervisor,
        )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["platform"], "web")
        self.assertEqual(result["generatedFiles"], ["index.html"])
        self.assertTrue(result["projectPath"].startswith(str((self.root / "output").resolve())))
        self.assertIsNone(result["finalUrl"])

    def test_web_failure_does_not_return_a_url_or_success(self):
        result = run_build(
            self.payload("web"),
            repository_root=self.root,
            llm_factory=lambda: object(),
            supervisor_factory=lambda **kwargs: FakeSupervisor(**kwargs, status="FAIL"),
        )
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["finalUrl"])
        self.assertEqual(result["error"]["message"], "Web execution failed")

    def test_mobile_dispatch_executes_crew_and_reports_generated_files(self):
        result = run_build(
            self.payload("mobile"),
            repository_root=self.root,
            llm_factory=lambda: object(),
            mobile_workflow_factory=FakeMobileWorkflow,
        )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["platform"], "mobile")
        self.assertEqual(result["generatedFiles"], ["App.js"])
        self.assertIsNone(result["finalUrl"])

    def test_mobile_qa_failure_is_preserved(self):
        result = run_build(
            self.payload("mobile"),
            repository_root=self.root,
            llm_factory=lambda: object(),
            mobile_workflow_factory=lambda **kwargs: FakeMobileWorkflow(
                **kwargs,
                qa_output='{"status":"fail","summary":"Invalid build","failures":["build"]}',
            ),
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["type"], "MobileQAFailed")

    def test_mobile_invalid_qa_output_is_not_reported_as_success(self):
        result = run_build(
            self.payload("mobile"),
            repository_root=self.root,
            llm_factory=lambda: object(),
            mobile_workflow_factory=lambda **kwargs: FakeMobileWorkflow(**kwargs, qa_output="unclear QA output"),
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["type"], "InvalidMobileQAResult")

    def test_scoped_writer_accepts_own_project_and_rejects_traversal(self):
        project_id = "web-" + self.job_id
        project_dir = self.root / "output" / project_id
        project_dir.mkdir()
        writer = WriteFileTool(output_dir=project_dir, project_id=project_id)

        outcome = writer._run(f"output/{project_id}/index.html::<h1>ok</h1>")
        self.assertIn("OK:", outcome)
        self.assertTrue((project_dir / "index.html").is_file())

        rejected = writer._run("../outside.txt::nope")
        self.assertTrue(rejected.startswith("ERROR:"))
        self.assertFalse((self.root / "output" / "outside.txt").exists())

        json_writer = WriteJsonResultTool(output_dir=project_dir, project_id=project_id)
        json_writer._run(f"output/{project_id}/result.json", {"status": "ok"})
        self.assertTrue((project_dir / "result.json").is_file())
        json_writer._run("../../outside.json", {"status": "unsafe"})
        self.assertFalse((self.root / "outside.json").exists())


if __name__ == "__main__":
    unittest.main()