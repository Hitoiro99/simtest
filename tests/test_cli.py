import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from simtest import main
from solvers.OpenFOAM.adapter import OpenFOAMAdapter


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.case_path = self.root / "cases" / "shear-decay-2d"
        shutil.copytree(ROOT / "cases" / "shear-decay-2d", self.case_path)
        self.case_file = self.case_path / "case.yaml"

    def invoke(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--root", str(self.root), *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def validate(self):
        info = SimpleNamespace(version="12", capabilities=["serial", "mpi"])
        adapter = OpenFOAMAdapter()
        with patch("simtest.select_install", return_value=({}, {}, info, adapter)):
            return self.invoke("validate", "shear-decay-2d")

    def test_validate_accepts_default_and_partial_execution(self):
        original = yaml.safe_load(self.case_file.read_text(encoding="utf-8"))
        for execution in (None, {"backend": "serial"}):
            with self.subTest(execution=execution):
                case = dict(original)
                if execution is None:
                    case.pop("execution")
                else:
                    case["execution"] = execution
                self.case_file.write_text(yaml.safe_dump(case), encoding="utf-8")
                code, stdout, stderr = self.validate()
                self.assertEqual(code, 0, stderr)
                self.assertTrue(json.loads(stdout)["valid"])

    def test_validate_rejects_ambiguous_field_mapping(self):
        case = yaml.safe_load(self.case_file.read_text(encoding="utf-8"))
        mappings = case["fields"]["velocity"]["mapping"]
        mappings.append(dict(mappings[0]))
        self.case_file.write_text(yaml.safe_dump(case), encoding="utf-8")
        code, stdout, stderr = self.validate()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("多个同时匹配的 mapping", json.loads(stderr)["message"])

    def test_validate_rejects_incomplete_native_mesh(self):
        (self.case_path / "polyMesh" / "boundary").unlink()
        code, stdout, stderr = self.invoke("list", "cases")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)[0]["id"], "shear-decay-2d")
        code, stdout, stderr = self.validate()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("网格缺少 boundary", json.loads(stderr)["message"])
        self.assertFalse((self.root / "runs").exists())

    def test_validate_rejects_native_template_layout_without_rendering(self):
        template = next((self.case_path / "templates").glob("*/template.yaml")).parent
        (template / "setup.jou").write_text("{{ missing | real }}", encoding="utf-8")
        code, stdout, stderr = self.validate()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("0/constant/system", json.loads(stderr)["message"])
        self.assertFalse((self.root / "runs").exists())

    def test_run_without_conditions_reports_missing_conditions(self):
        for condition in (self.case_path / "conditions").glob("*.yaml"):
            condition.unlink()
        code, stdout, stderr = self.invoke("run", "shear-decay-2d")
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["message"], "没有工况")
        self.assertFalse((self.root / "runs").exists())

    def test_run_reports_failed_jobs_and_returns_failure(self):
        results = [
            {"job_id": "job-a", "status": "SUCCEEDED"},
            {"job_id": "job-b", "status": "CRASHED"},
            {"job_id": "job-c", "status": "SUCCEEDED"},
            {"job_id": "job-d", "status": "SUCCEEDED"},
        ]
        with patch("simtest.prepare_job", return_value=(object(), object())), patch(
            "simtest.run_job", side_effect=results
        ), patch("report.report", return_value={"report": "report.html"}) as report:
            code, stdout, stderr = self.invoke(
                "run", "shear-decay-2d", "--solver", "OpenFOAM@12", "--solver", "OpenFOAM@latest"
            )
        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(len(stdout.splitlines()), 5)
        report.assert_called_once_with(self.root, "shear-decay-2d", ["job-a", "job-b", "job-c", "job-d"])

    def test_prepare_only_does_not_generate_report(self):
        with patch("simtest.prepare_job", return_value=(object(), object())) as prepare, patch(
            "simtest.run_job", return_value={"job_id": "prepared", "status": "QUEUED"}
        ), patch("report.report") as report:
            code, stdout, stderr = self.invoke("run", "shear-decay-2d", "--prepare-only")
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        lines = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual([item["status"] for item in lines], ["QUEUED", "QUEUED"])
        self.assertEqual(
            [call.kwargs["execution"]["name"] for call in prepare.call_args_list],
            ["serial-1proc", "mpi-2proc"],
        )
        report.assert_not_called()
