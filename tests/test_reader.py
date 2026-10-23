"""Fixed native result regression: topology, coordinates, time switching, values."""

import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

from solvers.OpenFOAM.versions.v12 import V12
from solvers.exceptions import FieldParseError

ROOT = Path(__file__).resolve().parents[1]
PVPYTHON = Path("/opt/paraviewopenfoam510/bin/pvpython")


def native_values(path):
    text = path.read_text()
    match = re.search(r"internalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;", text, re.S)
    if not match:
        raise AssertionError("Fixture field shape changed")
    values = [[float(v) for v in row.split()] for row in re.findall(r"\(([^()]+)\)", match.group(2))]
    if len(values) != int(match.group(1)):
        raise AssertionError("Fixture count mismatch")
    return values


@unittest.skipUnless(PVPYTHON.is_file(), "requires installed pvpython/VTK")
class ReaderRegression(unittest.TestCase):
    def test_native_all_times_and_serialized_minimal_arrays(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            case = directory / "case"
            shutil.copytree(ROOT / "tests" / "fixtures" / "openfoam12", case)
            time_raw = (case / "1" / "uniform" / "time").read_text()
            actual_time = float(re.search(r"(?m)^value\s+([^;]+);", time_raw).group(1))
            request = {
                "mode": "native",
                "case": str(case),
                "times": [
                    {"name": "0", "reader_time": 0, "time": 0},
                    {"name": "1", "reader_time": 1, "time": actual_time},
                ],
                "fields": [
                    {
                        "canonical": "velocity",
                        "native": "U",
                        "factor": 1,
                        "unit": "m/s",
                        "domain": "internalMesh",
                        "components": 3,
                    }
                ],
                "output": str(directory / "normalized"),
                "response": str(directory / "response.json"),
            }
            file = directory / "request.json"
            file.write_text(json.dumps(request))
            subprocess.run(
                [
                    str(PVPYTHON),
                    "--force-offscreen-rendering",
                    str(ROOT / "solvers" / "OpenFOAM" / "vtk_bridge.py"),
                    str(file),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
            )
            datasets = json.loads((directory / "response.json").read_text())["datasets"]
            self.assertEqual(len(datasets), 2)
            self.assertEqual([d["time"] for d in datasets], [0, actual_time])
            for dataset, label in zip(datasets, ("0", "1")):
                values = native_values(case / label / "U")
                self.assertEqual(dataset["cells"], 128)
                self.assertEqual(dataset["points"], 330)
                self.assertEqual(
                    set(dataset["arrays"]),
                    {
                        "velocity",
                        "velocity_x",
                        "velocity_y",
                        "velocity_z",
                        "velocity_magnitude",
                        "cell_volume",
                        "cell_center",
                        "original_cell_id",
                    },
                )
                for sample, target in zip(dataset["samples"], values):
                    self.assertGreater(sample["volume"], 0)
                    self.assertTrue(0 <= sample["center"][1] <= 0.1)
                    for value, expected in zip(sample["value"], target):
                        # The bundled reader stores Float32 arrays. This is a
                        # decoder fidelity bound, not a numerical acceptance threshold.
                        self.assertTrue(math.isclose(value, expected, rel_tol=2e-7, abs_tol=1e-12), (value, expected))
            self.assertLess(datasets[1]["samples"][64]["value"][0], datasets[0]["samples"][64]["value"][0])


class AdapterReaderOverrides(unittest.TestCase):
    def test_monitor_reader_uses_version_log_and_table_methods(self):
        calls = []

        class VersionAdapter(V12):
            def read_log(self, path):
                calls.append("log")
                return [1.0], {"residual:Ux": {(1, 1.0): 0.125}}, []

            def read_tables(self, work):
                calls.append("tables")
                return {"flow": {1.0: 2.5}}, []

            def dictionary(self, context, path, entry=None, keywords=False):
                calls.append(entry)
                return "0;"

        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            context = SimpleNamespace(
                run_dir=directory, work=directory / "work", input=directory / "input",
                normalized=directory / "normalized", manifest={},
                case={"monitors": {"residual:Ux": {}, "flow": {}}},
            )
            records, warnings = VersionAdapter().read_monitors(context)
            self.assertEqual(calls, ["log", "tables", "startTime"])
            self.assertEqual(records["residual:Ux"][0].value, 0.125)
            self.assertEqual(records["flow"][0].value, 2.5)
            self.assertEqual(records["flow"][0].step, 1)
            self.assertEqual(context.manifest["solver_time_axis"], {"start": 0.0, "steps": [1.0]})
            self.assertEqual(warnings, [])
            self.assertEqual((context.normalized / "monitors.csv").read_text().splitlines(),
                             ["step,time,residual:Ux,flow", "1,1.0,0.125,2.5"])

    def test_field_reader_uses_version_output_time_method(self):
        class VersionAdapter(V12):
            def output_times(self, context):
                raise FieldParseError("version-specific time metadata")

        context = SimpleNamespace(condition={"references": {"reference": {"field": "velocity"}}})
        with self.assertRaisesRegex(FieldParseError, "version-specific time metadata"):
            VersionAdapter().read_fields(context)

    def test_postprocess_uses_version_reader_methods_after_reconstruction(self):
        calls = []
        warning = {"kind": "invalid", "monitor": "flow"}
        datasets = [{"field": "velocity"}]

        class VersionAdapter(V12):
            def native(self, context, tool, args, label, case_path=None):
                calls.append(tool)

            def read_monitors(self, context):
                calls.append("monitors")
                record = SimpleNamespace(step=1, time=1.0, value=2.5, quality="valid")
                return {"flow": [record]}, [warning]

            def read_fields(self, context):
                calls.append("fields")
                return datasets

        context = SimpleNamespace(execution={"processes": 2}, diagnostics=[], manifest={}, normalized=Path("normalized"))
        result = VersionAdapter().postprocess(context)
        self.assertEqual(calls, ["reconstructPar", "monitors", "fields"])
        self.assertEqual(context.diagnostics, [warning])
        self.assertEqual(context.manifest["monitors"]["flow"],
                         [{"step": 1, "time": 1.0, "value": 2.5, "quality": "valid"}])
        self.assertEqual(result.diagnostics["fields"], datasets)
        self.assertEqual(result.warnings, [warning])
