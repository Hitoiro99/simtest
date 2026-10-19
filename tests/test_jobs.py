"""稳定作业身份、复用、失败保留与并发单写回归。"""

import copy
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import jobs
from common.io import inventory
from solvers.exceptions import ConfigurationError, PostprocessError, SolverCrashError
from solvers.models import SolverInfo, StageResult


class JobAdapter:
    name = "TestSolver"
    version = "1"
    version_rule = "integer"
    environment_keys = ("OMP_NUM_THREADS",)

    def __init__(self, fail=False, counter=None):
        self.fail = fail
        self.counter = counter
        self.preparations = 0
        self.executions = 0

    def validate(self, context):
        return None

    def preprocess(self, context):
        self.preparations += 1
        context.input.mkdir()
        (context.input / "settings").write_text("endTime=1\ndeltaT=0.1\n", encoding="utf-8")
        context.work.mkdir()
        (context.work / "settings").write_text("endTime=1\ndeltaT=0.1\n", encoding="utf-8")
        context.manifest["input_sha256"] = inventory(context.input)
        return StageResult()

    def execute(self, context):
        self.executions += 1
        (context.run_dir / "logs" / "solver.log").write_text("Time=1\nEnd\n", encoding="utf-8")
        if self.counter:
            with Path(self.counter).open("a", encoding="utf-8") as stream:
                stream.write("execute\n")
            time.sleep(0.2)
        if self.fail:
            raise SolverCrashError("controlled crash")
        return StageResult(diagnostics={"elapsed": 0.1, "peak_memory_bytes": 1024})

    def postprocess(self, context):
        context.normalized.mkdir()
        (context.normalized / "monitors.csv").write_text("step,time\n1,1\n", encoding="utf-8")
        return StageResult(diagnostics={"fields": []})


def concurrent_job(context, adapter, gate, output):
    gate.wait(10)
    try:
        output.put(jobs.run_job(context, adapter))
    except Exception as exc:
        output.put({"error": repr(exc)})


@unittest.skipUnless(os.name == "posix", "Linux/WSL 作业文件锁")
class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case_path = self.root / "cases" / "sample"
        (self.case_path / "conditions").mkdir(parents=True)
        (self.case_path / "mesh.msh").write_text("mesh-v1", encoding="utf-8")
        self.case_file = self.case_path / "case.yaml"
        self.case_file.write_text(
            'id: sample\nversion: "1"\nvariables:\n'
            '  end_time: {type: real, required: true}\n'
            '  delta_t: {type: real, required: true}\n'
            '  output_interval: {type: integer, required: true}\n', encoding="utf-8"
        )
        self.condition_file = self.case_path / "conditions" / "default.yaml"
        self.write_condition()
        executable = self.root / "solver"
        executable.write_text("solver-binary-v1", encoding="utf-8")
        self.info = SolverInfo("TestSolver", "1", "build-a", "main", ["serial", "mpi"], {"solver": str(executable)})
        self.installation = {"path": str(self.root), "environment": {"kind": "existing"}}
        self.environment = {"OMP_NUM_THREADS": "1"}
        self.adapter = JobAdapter()
        self.hardware = {"machine": "machine-a", "cpu": "cpu-a", "memory_bytes": 1024, "gpus": []}
        self.codes = {"jobs.py": "code-v1"}
        self.options = SimpleNamespace(
            config=None, processes=None, backend=None, openmp_threads=None, timeout=30, heartbeat_timeout=10
        )
        for target, kwargs in (
            ("jobs.select_install", {"side_effect": self.install}),
            ("jobs.hardware_info", {"side_effect": lambda *args: copy.deepcopy(self.hardware)}),
            ("jobs.code_inventory", {"side_effect": lambda: dict(self.codes)}),
            ("jobs._git_revision", {"return_value": "commit-a"}),
        ):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def install(self, *args):
        return copy.deepcopy(self.installation), dict(self.environment), copy.deepcopy(self.info), self.adapter

    def write_condition(self, end_time=1, delta_t=0.1, output_interval=1):
        self.condition_file.write_text(
            "values:\n  end_time: {value: %s}\n  delta_t: {value: %s}\n  output_interval: {value: %s}\n"
            % (end_time, delta_t, output_interval), encoding="utf-8"
        )

    def prepare(self):
        return jobs.prepare_job(self.root, "sample", "default", "TestSolver@1", self.options)[0]

    def test_identity_is_stable_and_prepare_has_no_side_effect(self):
        first = self.prepare()
        time.sleep(0.002)
        with patch("jobs._git_revision", return_value="documentation-only-commit"):
            second = self.prepare()
        self.assertRegex(first.run_dir.name, r"^[0-9a-f]{64}$")
        self.assertEqual(first.run_dir.name, second.run_dir.name)
        self.assertNotEqual(first.manifest["created"], second.manifest["created"])
        self.assertNotIn("nonce", first.manifest["identity"])
        self.options.timeout = float(self.options.timeout)
        self.options.heartbeat_timeout = float(self.options.heartbeat_timeout)
        self.assertEqual(first.run_dir.name, self.prepare().run_dir.name)
        self.assertFalse((self.root / "runs").exists())
        first.manifest["execution_result"] = {"elapsed": 999, "peak_memory_bytes": 999}
        self.assertEqual(first.manifest["identity"], second.manifest["identity"])

    def test_simulation_settings_and_input_content_change_identity(self):
        original = self.prepare().run_dir.name
        for values in ((2, 0.1, 1), (1, 0.2, 1), (1, 0.1, 2)):
            with self.subTest(values=values):
                self.write_condition(*values)
                self.assertNotEqual(original, self.prepare().run_dir.name)
        self.write_condition()
        (self.case_path / "mesh.msh").write_text("mesh-v2", encoding="utf-8")
        self.assertNotEqual(original, self.prepare().run_dir.name)

    def test_carrier_solver_execution_and_environment_change_identity(self):
        original = self.prepare().run_dir.name
        changes = (
            (self.options, "processes", 2),
            (self.info, "build", "build-b"),
            (self.info, "version", "2"),
        )
        for obj, name, value in changes:
            with self.subTest(field=name):
                saved = getattr(obj, name)
                setattr(obj, name, value)
                self.assertNotEqual(original, self.prepare().run_dir.name)
                setattr(obj, name, saved)
        for mapping, key, value in (
            (self.hardware, "machine", "machine-b"),
            (self.hardware, "memory_bytes", 2048),
            (self.codes, "jobs.py", "code-v2"),
            (self.environment, "OMP_NUM_THREADS", "2"),
        ):
            with self.subTest(field=key):
                saved = mapping[key]
                mapping[key] = value
                self.assertNotEqual(original, self.prepare().run_dir.name)
                mapping[key] = saved
        Path(self.info.executables["solver"]).write_text("solver-binary-v2", encoding="utf-8")
        self.assertNotEqual(original, self.prepare().run_dir.name)

    def test_success_reuses_archive_without_workspace_or_execution(self):
        context = self.prepare()
        first = jobs.run_job(context, self.adapter)
        self.assertEqual(first["status"], "SUCCEEDED")
        self.assertFalse(first["reused"])
        self.assertFalse(context.run_dir.exists())
        archived_manifest = (Path(first["archive"]) / "manifest.json").read_bytes()
        second = jobs.run_job(self.prepare(), self.adapter)
        self.assertTrue(second["reused"])
        self.assertEqual(first["job_id"], second["job_id"])
        self.assertEqual(self.adapter.executions, 1)
        self.assertFalse(context.run_dir.exists())
        self.assertEqual(archived_manifest, (Path(first["archive"]) / "manifest.json").read_bytes())

    def test_prepared_job_resumes_without_repeating_preprocess(self):
        context = self.prepare()
        first = jobs.run_job(context, self.adapter, prepare_only=True)
        self.assertEqual(first["status"], "QUEUED")
        second = jobs.run_job(self.prepare(), self.adapter, prepare_only=True)
        self.assertTrue(second["reused"])
        result = jobs.run_job(self.prepare(), self.adapter)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(self.adapter.preparations, 1)
        self.assertEqual(self.adapter.executions, 1)
        self.assertFalse(context.run_dir.exists())

    def test_prepared_work_tamper_is_rejected_and_retained(self):
        context = self.prepare()
        jobs.run_job(context, self.adapter, prepare_only=True)
        (context.work / "settings").write_text("tampered", encoding="utf-8")
        result = jobs.run_job(self.prepare(), self.adapter)
        self.assertEqual(result["status"], "INFRA_ERROR")
        self.assertEqual(self.adapter.executions, 0)
        self.assertTrue(context.work.exists())
        self.assertFalse(jobs.archive_path(context).exists())

    def test_failure_is_not_retried_or_archived(self):
        self.adapter.fail = True
        context = self.prepare()
        first = jobs.run_job(context, self.adapter)
        self.assertEqual(first["status"], "CRASHED")
        original_status = (context.run_dir / "status.json").read_bytes()
        self.adapter.fail = False
        second = jobs.run_job(self.prepare(), self.adapter)
        self.assertEqual(second["status"], "CRASHED")
        self.assertTrue(second["reused"])
        self.assertEqual(self.adapter.executions, 1)
        self.assertEqual(original_status, (context.run_dir / "status.json").read_bytes())
        self.assertTrue(context.work.exists())
        self.assertFalse(jobs.archive_path(context).exists())

    def test_damaged_archive_is_neither_reused_nor_overwritten(self):
        context = self.prepare()
        first = jobs.run_job(context, self.adapter)
        file = Path(first["archive"]) / "normalized" / "monitors.csv"
        file.write_text("broken", encoding="utf-8")
        with self.assertRaises((ConfigurationError, PostprocessError)):
            jobs.run_job(self.prepare(), self.adapter)
        self.assertEqual(self.adapter.executions, 1)
        self.assertEqual(file.read_text(encoding="utf-8"), "broken")

    def test_cleanup_failure_retries_cleanup_without_recomputation(self):
        context = self.prepare()
        with patch("jobs.cleanup_run", side_effect=PermissionError("busy")):
            first = jobs.run_job(context, self.adapter)
        self.assertEqual(first["status"], "SUCCEEDED")
        self.assertTrue(first["cleanup_pending"])
        self.assertTrue(context.work.exists())
        import json

        status = json.loads((context.run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "SUCCEEDED")
        self.assertTrue(status["cleanup_pending"])
        second = jobs.run_job(self.prepare(), self.adapter)
        self.assertTrue(second["reused"])
        self.assertFalse(second.get("cleanup_pending", False))
        self.assertFalse(context.run_dir.exists())
        self.assertEqual(self.adapter.executions, 1)

    def test_prepared_only_reuse_rejects_tampered_input(self):
        context = self.prepare()
        jobs.run_job(context, self.adapter, prepare_only=True)
        (context.input / "settings").write_text("tampered", encoding="utf-8")
        result = jobs.run_job(self.prepare(), self.adapter, prepare_only=True)
        self.assertEqual(result["status"], "INFRA_ERROR")
        self.assertEqual(self.adapter.executions, 0)
        self.assertTrue(context.work.exists())

    def test_cleanup_refusal_does_not_reclassify_success(self):
        context = self.prepare()
        with patch("jobs.cleanup_run", side_effect=PostprocessError("unsafe cleanup refused")):
            result = jobs.run_job(context, self.adapter)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertTrue(result["cleanup_pending"])
        self.assertTrue(jobs.verify_archive(Path(result["archive"])))
        self.assertEqual(self.adapter.executions, 1)

    def test_concurrent_identical_jobs_have_one_writer(self):
        process_context = multiprocessing.get_context("fork")
        gate = process_context.Event()
        output = process_context.Queue()
        counter = self.root / "execution-count"
        self.adapter.counter = str(counter)
        contexts = [self.prepare(), self.prepare()]
        children = [
            process_context.Process(target=concurrent_job, args=(context, self.adapter, gate, output))
            for context in contexts
        ]
        try:
            for child in children:
                child.start()
            gate.set()
            results = [output.get(timeout=20), output.get(timeout=20)]
            for child in children:
                child.join(20)
                self.assertEqual(child.exitcode, 0)
            self.assertEqual([result.get("status") for result in results], ["SUCCEEDED", "SUCCEEDED"])
            self.assertEqual(sorted(result["reused"] for result in results), [False, True])
            self.assertEqual(counter.read_text(encoding="utf-8"), "execute\n")
            self.assertFalse(contexts[0].run_dir.exists())
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join(5)
            output.close()
            output.join_thread()


if __name__ == "__main__":
    unittest.main()
