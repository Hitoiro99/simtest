import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from archive import archive, verify_archive
from solvers.registry import load_env
from common.io import atomic_json, inventory
from solvers.exceptions import PostprocessError, SolverCrashError
from solvers.OpenFOAM.adapter import OpenFOAMAdapter
from solvers.base import supervise as real_supervise

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(Path("/opt/openfoam12/etc/bashrc").is_file(), "requires installed OpenFOAM 12")
class IntegrationTests(unittest.TestCase):
    def test_native_failure_exports_and_reads_all_times(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work = root / "work"
            shutil.copytree(ROOT / "tests" / "fixtures" / "openfoam12", work)
            (root / "logs").mkdir()
            environment = load_env({"environment": {"kind": "script", "script": "/opt/openfoam12/etc/bashrc"}})
            adapter = OpenFOAMAdapter()
            info = adapter.probe(SimpleNamespace(environment=environment))
            reference = {"field": "velocity", "domain": "internalMesh", "expression": {"x": "0", "y": "0", "z": "0"}}
            context = SimpleNamespace(
                work=work,
                input=root / "input",
                normalized=root / "normalized",
                run_dir=root,
                environment=environment,
                info=info,
                timeout=60,
                heartbeat_timeout=30,
                diagnostics=[],
                condition={"references": {"r": reference}},
                case={
                    "fields": {
                        "velocity": {"type": "real", "unit": "m/s", "mapping": [{"solver": "OpenFOAM", "name": "U"}]}
                    }
                },
                manifest={
                    "solver_time_axis": {
                        "start": 0,
                        "steps": [float(format(i * 0.001, ".12g")) for i in range(1, 1001)],
                    }
                },
            )

            def unavailable_native(command, *args, **kwargs):
                if command.argv[0] == info.executables["pvpython"]:
                    request = json.loads(Path(command.argv[-1]).read_text())
                    if request["mode"] == "native":
                        raise SolverCrashError("simulated unavailable native reader")
                return real_supervise(command, *args, **kwargs)

            with patch("solvers.base.supervise", side_effect=unavailable_native):
                data = adapter.read_fields(context)
            self.assertEqual(context.manifest["field_reader"]["mode"], "exchange")
            self.assertEqual(len(data), 2)
            self.assertEqual([entry["cells"] for entry in data], [128, 128])
            self.assertLess(data[1]["samples"][64]["value"][0], data[0]["samples"][64]["value"][0])
            self.assertTrue((context.normalized / "fields" / "fields.pvd").is_file())
            self.assertTrue(any(d["kind"] == "reader_fallback" for d in context.diagnostics))

    def test_archive_validation_failure_keeps_raw_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "runs" / "testjob"
            (run / "work").mkdir(parents=True)
            (run / "work" / "raw.dat").write_text("important raw result")
            (run / "input").mkdir()
            (run / "input" / "dict").write_text("original input")
            (run / "logs").mkdir()
            (run / "normalized").mkdir()
            (run / "normalized" / "monitors.csv").write_text("step,time,a\n0,0,1\n")
            context = SimpleNamespace(
                root=root,
                run_dir=run,
                input=run / "input",
                work=run / "work",
                normalized=run / "normalized",
                case={"id": "case", "monitors": {"a": {}}},
                condition_id="condition",
                info=SimpleNamespace(name="OpenFOAM", version="12"),
                manifest={"input_sha256": inventory(run / "input"), "fields": []},
            )
            atomic_json(run / "manifest.json", context.manifest)
            (run / "input" / "dict").write_text("corrupted input")
            with self.assertRaises(PostprocessError):
                archive(context, {"status": "SUCCEEDED"})
            self.assertTrue((run / "work" / "raw.dat").is_file())
