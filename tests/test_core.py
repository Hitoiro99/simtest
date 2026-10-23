import csv
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from analysis import field_comparisons, monitor_comparisons
from archive import archive, verify_archive
from case_management.cases import execution_config, execution_configs, load_case, load_condition, mesh_asset
from platform_support.expression import evaluate
from platform_support.io import read_yaml
from case_management.templates import materialize
from platform_support.units import convert
from solvers.base import SolverAdapter, supervise
from solvers.exceptions import (
    ConfigurationError,
    MeshConversionError,
    PostprocessError,
    PreprocessError,
    SolverTimeoutError,
    UnsupportedCaseError,
)
from solvers.models import Command, RunContext, SolverInfo
from solvers.OpenFOAM.versions.v12 import V12
from solvers.registry import ADAPTERS, compatibility, discover, mapped, register_adapter, select


class TemplateAdapter(SolverAdapter):
    """用于检查公共模板边界的测试内核，不登记为可运行求解器。"""

    name = "TemplateTest"
    version = "1"

    @staticmethod
    def version_key(version):
        return int(version)

    def probe(self, context):
        raise NotImplementedError

    def validate(self, context):
        raise NotImplementedError

    def preprocess(self, context):
        raise NotImplementedError

    def build(self, context):
        raise NotImplementedError

    def postprocess(self, context):
        raise NotImplementedError


class CoreTests(unittest.TestCase):
    def test_duplicate_yaml_key(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "case.yaml"
            file.write_text("a: 1\na: 2\n")
            with self.assertRaises(ConfigurationError):
                read_yaml(file)

    def test_restricted_expression(self):
        self.assertAlmostEqual(
            evaluate("A*sin(pi*y/H)*exp(-nu*(pi/H)**2*t)", {"A": 0.1, "y": 0.05, "H": 0.1, "nu": 0.001, "t": 0}), 0.1
        )
        for expression in (
            "__import__('os')",
            "x.__class__",
            "x[0]",
            "[x for x in []]",
            "2**10000",
            "1/0",
            "exp(10000)",
        ):
            with self.subTest(expression=expression), self.assertRaises(ConfigurationError):
                evaluate(expression, {"x": 1})

    def test_units_and_integer_parallel_validation(self):
        self.assertAlmostEqual(convert(100, "cm/s", "m/s"), 1)
        self.assertAlmostEqual(convert(1, "g/cm^3", "kg/m^3"), 1000)
        with self.assertRaises(ConfigurationError):
            convert(1, "Pa", "m/s")
        for config in (
            {"processes": True},
            {"processes": 0},
            {"backend": "serial", "openmp_threads": 2},
            {"backend": "openmp"},
        ):
            with self.assertRaises(ConfigurationError):
                execution_config(config)

    def test_execution_profiles_support_single_and_list_forms(self):
        single = execution_configs({"backend": "serial", "processes": 1})
        self.assertEqual([profile["processes"] for profile in single], [1])
        profiles = execution_configs([
            {"name": "serial-1proc", "backend": "serial", "processes": 1},
            {"name": "mpi-2proc", "backend": "serial", "processes": 2},
        ])
        self.assertEqual([profile["name"] for profile in profiles], ["serial-1proc", "mpi-2proc"])
        self.assertEqual([profile["processes"] for profile in profiles], [1, 2])
        for value in ([], [{"name": "a"}, {"name": "a"}], [1], "serial"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                execution_configs(value)

    def test_multiple_parameters_not_limited_to_example(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "case1"
            path.mkdir()
            (path / "conditions").mkdir()
            (path / "polyMesh").mkdir()
            for name in ("points", "faces", "owner", "neighbour", "boundary"):
                (path / "polyMesh" / name).touch()
            (path / "case.yaml").write_text(
                'id: case1\nversion: "1"\nexecution: {backend: serial, processes: 1}\nconstants:\n  a: {type: real, value: 1}\n  b: {type: real, value: 2}\nvariables:\n  u: {type: real, required: true, unit: m/s}\n  v: {type: real, required: true}\nderived_variables:\n  sum: {type: real, expression: "a+b+u+v"}\n'
            )
            condition = path / "conditions" / "first.yaml"
            condition.write_text("values:\n  u: {value: 100, unit: cm/s}\n  v: {value: 3}\n")
            case = load_case(path)
            values, resolved = load_condition(path, case, "first")
            self.assertEqual(resolved["sum"], 7)
            condition.write_text("values: {a: {value: 2}}\n")
            with self.assertRaises(ConfigurationError):
                load_condition(path, case, "first")
            condition.write_text("values: {u: {value: 1, unit: m/s}}\n")
            with self.assertRaises(ConfigurationError):
                load_condition(path, case, "first")

    def test_namespace_collision(self):
        root = Path(__file__).resolve().parents[1]
        original = read_yaml(root / "cases" / "couette-2d" / "case.yaml")
        with tempfile.TemporaryDirectory() as temp:
            import yaml

            path = Path(temp) / original["id"]
            path.mkdir()
            (path / "polyMesh").mkdir()
            for name in ("points", "faces", "owner", "neighbour", "boundary"):
                (path / "polyMesh" / name).touch()
            original["variables"]["kinematic_viscosity"] = {"type": "real"}
            (path / "case.yaml").write_text(yaml.safe_dump(original))
            with self.assertRaises(ConfigurationError):
                load_case(path)

    def test_version_and_mapping_ambiguity(self):
        discover()
        adapter = select("OpenFOAM", "12")
        self.assertEqual(adapter.version, "12")
        self.assertEqual(select("OpenFOAM", "13").version, "12")
        with self.assertRaises(UnsupportedCaseError):
            select("OpenFOAM", "11")
        with self.assertRaises(UnsupportedCaseError):
            select("OpenFOAM", "v2312")
        self.assertEqual(compatibility("12", adapter), (True, 3))
        with self.assertRaises(ConfigurationError):
            compatibility(">=11", adapter)
        with self.assertRaises(ConfigurationError):
            mapped(
                {"mapping": [{"solver": "OpenFOAM", "name": "a"}, {"solver": "OpenFOAM", "name": "b"}]}, "x", adapter
            )

    def test_template_undefined_and_integer_filter(self):
        adapter = V12()
        for value in (1.2, True, float("nan")):
            with self.assertRaises(ConfigurationError):
                adapter.format_integer(value)
        for value in (float("nan"), float("inf"), True):
            with self.assertRaises(ConfigurationError):
                adapter.format_real(value)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "templates" / "OpenFOAM"
            (template / "system").mkdir(parents=True)
            (template / "template.yaml").write_text('id: t\nsolver: OpenFOAM\ncompatibility: "12"\n')
            (template / "system" / "controlDict").write_text("{{ missing | real }}")
            context = SimpleNamespace(
                case_path=root,
                input=root / "input",
                parameters={},
                execution={},
                info=SimpleNamespace(name="OpenFOAM", version="12"),
                condition_id="c",
                manifest={},
            )
            with self.assertRaises(PreprocessError):
                materialize(context, adapter)

    def template_context(self, root, adapter, name="input"):
        return SimpleNamespace(
            case_path=root,
            input=root / name,
            parameters={"amplitude": 3},
            execution={},
            info=SimpleNamespace(name=adapter.name, version=adapter.version),
            condition_id="default",
            manifest={},
        )

    def test_mesh_discovery_is_separate_from_native_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sample"
            root.mkdir()
            (root / "case.yaml").write_text('id: sample\nversion: "1"\n', encoding="utf-8")
            mesh = root / "polyMesh"
            mesh.mkdir()
            self.assertEqual(load_case(root)["id"], "sample")
            self.assertEqual(mesh_asset(root), mesh)
            adapter = V12()
            context = SimpleNamespace(
                case_path=root,
                case={},
                execution={"backend": "serial", "processes": 1},
                info=SimpleNamespace(capabilities=["serial"]),
            )
            for name in ("points", "faces", "owner", "neighbour", "boundary"):
                with self.subTest(missing=name), self.assertRaisesRegex(ConfigurationError, "网格缺少 " + name):
                    adapter.validate(context)
                (mesh / name).touch()
            adapter.validate(context)
            (root / "mesh.cgns").touch()
            with self.assertRaisesRegex(ConfigurationError, "有且只有一个"):
                mesh_asset(root)
            for file in mesh.iterdir():
                file.unlink()
            mesh.rmdir()
            self.assertEqual(mesh_asset(root).name, "mesh.cgns")
            with self.assertRaises(MeshConversionError):
                adapter.validate(context)

    def test_other_solver_template_layout_and_filter_isolation(self):
        class AlternateAdapter(TemplateAdapter):
            def format_real(self, value):
                return "alternate-" + super().format_real(value)

        with tempfile.TemporaryDirectory() as temp, patch.dict(ADAPTERS, {"TemplateTest": {"1": TemplateAdapter}}):
            root = Path(temp)
            template = root / "templates" / "native"
            template.mkdir(parents=True)
            (template / "template.yaml").write_text('id: native\nsolver: TemplateTest\ncompatibility: "1"\n')
            names = ("setup.jou", "setup.java", "setup.json")
            for name in names:
                (template / name).write_text("{{ amplitude | real }}")
            for index, adapter in enumerate((TemplateAdapter(), AlternateAdapter(), TemplateAdapter())):
                context = self.template_context(root, adapter, "input-" + str(index))
                materialize(context, adapter)
                expected = "alternate-3.0" if index == 1 else "3.0"
                for name in names:
                    self.assertEqual((context.input / name).read_text(), expected)
                self.assertEqual(set(context.manifest["rendered_sha256"]), set(names))

    def test_openfoam_template_layout_can_be_overridden_by_version(self):
        class ChangedLayout(V12):
            def validate_template(self, path):
                if path.parts[0] != "extra":
                    super().validate_template(path)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "templates" / "OpenFOAM"
            (template / "extra").mkdir(parents=True)
            (template / "template.yaml").write_text('id: native\nsolver: OpenFOAM\ncompatibility: "12"\n')
            (template / "extra" / "settings").write_text("{{ amplitude | real }}")
            adapter = V12()
            context = self.template_context(root, adapter)
            with self.assertRaisesRegex(ConfigurationError, "0/constant/system"):
                materialize(context, adapter)
            self.assertFalse(context.input.exists())
            materialize(context, ChangedLayout())
            self.assertEqual((context.input / "extra" / "settings").read_text(), "3.0")

    def test_template_inheritance_renders_only_final_files(self):
        adapter = V12()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root / "templates" / "parent"
            child = root / "templates" / "child"
            (parent / "system").mkdir(parents=True)
            (child / "system").mkdir(parents=True)
            (parent / "template.yaml").write_text('id: parent\nsolver: OpenFOAM\ncompatibility: "*"\n')
            (child / "template.yaml").write_text(
                'id: child\nsolver: OpenFOAM\ncompatibility: "12"\nextends: parent\n'
            )
            (parent / "system" / "controlDict").write_text("{{ missing | real }}")
            (child / "system" / "controlDict").write_text("{{ amplitude | real }}")
            context = self.template_context(root, adapter)
            with patch.object(adapter, "format_real", wraps=adapter.format_real) as real:
                materialize(context, adapter)
            real.assert_called_once_with(3)
            self.assertEqual(context.manifest["template"]["chain"], ["parent", "child"])
            self.assertEqual((context.input / "system" / "controlDict").read_text(), "3.0")
            self.assertEqual((parent / "system" / "controlDict").read_text(), "{{ missing | real }}")

    def test_templates_reject_embedded_source_meshes(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(ADAPTERS, {"TemplateTest": {"1": TemplateAdapter}}):
            root = Path(temp)
            template = root / "templates" / "native"
            template.mkdir(parents=True)
            (template / "template.yaml").write_text('id: native\nsolver: TemplateTest\ncompatibility: "1"\n')
            adapter = TemplateAdapter()
            for name in ("mesh.cgns", "mesh.msh", "polyMesh"):
                with self.subTest(name=name):
                    file = template / name
                    file.write_text("second mesh")
                    context = self.template_context(root, adapter)
                    with self.assertRaisesRegex(ConfigurationError, "模板不能另带网格"):
                        materialize(context, adapter)
                    self.assertFalse(context.input.exists())
                    file.unlink()

    @unittest.skipUnless(os.name == "posix", "Linux template symlinks")
    def test_templates_reject_symlinks_before_adapter_checks(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(ADAPTERS, {"TemplateTest": {"1": TemplateAdapter}}):
            root = Path(temp)
            template = root / "templates" / "native"
            template.mkdir(parents=True)
            (template / "template.yaml").write_text('id: native\nsolver: TemplateTest\ncompatibility: "1"\n')
            outside = root / "outside.jou"
            outside.write_text("outside")
            (template / "setup.jou").symlink_to(outside)
            adapter = TemplateAdapter()
            context = self.template_context(root, adapter)
            with patch.object(adapter, "validate_template") as check:
                with self.assertRaisesRegex(ConfigurationError, "符号链接"):
                    materialize(context, adapter)
                check.assert_not_called()
            self.assertFalse(context.input.exists())

    def test_monitor_record_boundaries_and_invalid_last(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "logs").mkdir()
            (root / "work" / "postProcessing" / "f" / "0").mkdir(parents=True)
            (root / "logs" / "solver.log").write_text("Time = 0.001s\nTime = 0.002s\nTime = 0.003s\n")
            (root / "work" / "postProcessing" / "f" / "0" / "a.dat").write_text("# Time a\n0.001 1\n0.003 nan\n")
            (root / "work" / "postProcessing" / "f" / "0" / "b.dat").write_text("# Time b\n0.001 2\n0.002 3\n")
            context = SimpleNamespace(
                run_dir=root,
                work=root / "work",
                input=root / "input",
                normalized=root / "normalized",
                case={"monitors": {"a": {"type": "real"}, "b": {"type": "real"}}},
                manifest={},
            )
            adapter = V12()
            adapter.dictionary = lambda *args, **kwargs: "0"
            records, warnings = adapter.read_monitors(context)
            self.assertEqual(records["b"][-1].step, 2)
            self.assertEqual(records["a"][-1].quality, "invalid")
            self.assertTrue(any(w["kind"] == "invalid" for w in warnings))
            with (context.normalized / "monitors.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[-1]["b"], "")
            context.manifest["monitors"] = {k: [r.__dict__ for r in v] for k, v in records.items()}
            context.condition = {
                "references": {"ref": {"monitor": "a", "value": 1, "reference_scale": {"value": 1}, "source": None}}
            }
            comparison = monitor_comparisons(context)[0]
            self.assertEqual(comparison["status"], "UNAVAILABLE")
            self.assertEqual(comparison["step"], 3)

    def test_vector_magnitude_is_difference_of_norms(self):
        context = SimpleNamespace(
            case={"fields": {"u": {"unit": "m/s"}}},
            condition={
                "references": {
                    "r": {
                        "field": "u",
                        "domain": "internalMesh",
                        "expression": {"x": "-1", "y": "0", "z": "0"},
                        "parameters": {},
                        "reference_scale": {"value": 1, "unit": "m/s"},
                        "source": {},
                    }
                }
            },
        )
        dataset = {
            "field": "u",
            "domain": "internalMesh",
            "time": 0,
            "samples": [{"value": [1, 0, 0], "center": [0, 0, 0], "volume": 2, "cell_id": 0}],
        }
        rows = field_comparisons(context, [dataset])
        self.assertEqual(next(r for r in rows if r["component"] == "x")["absolute_error"]["max"], 2)
        self.assertEqual(next(r for r in rows if r["component"] == "magnitude")["absolute_error"]["max"], 0)
        dataset["samples"][0]["volume"] = 0
        self.assertTrue(all(r["status"] == "UNAVAILABLE" for r in field_comparisons(context, [dataset])))

    def test_bad_value_preserves_last_record(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "postProcessing" / "m"
            path.mkdir(parents=True)
            (path / "m.dat").write_text("# Time a\n0 1\n1 broken\n")
            tables, warnings = V12().read_tables(Path(temp))
            self.assertTrue(math.isnan(tables["a"][1]))
            self.assertTrue(warnings)

    def test_archive_corruption_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            from test_archive import make_context

            context = make_context(temp)
            path = archive(context, {"status": "SUCCEEDED"})
            self.assertTrue(verify_archive(path))
            (path / "normalized" / "monitors.csv").write_text("broken")
            with self.assertRaises(PostprocessError):
                verify_archive(path)

    @unittest.skipUnless(os.name == "posix", "Linux process supervision")
    def test_timeout_stops_process_group(self):
        import sys

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            script = "import subprocess,time; from pathlib import Path; p=subprocess.Popen(['sleep','30']); Path('child.pid').write_text(str(p.pid)); time.sleep(30)"
            with self.assertRaises(SolverTimeoutError):
                supervise(Command([sys.executable, "-c", script], path, dict(os.environ), 0.2, None), path / "log")
            child = int((path / "child.pid").read_text())
            stat = Path("/proc") / str(child) / "stat"
            if stat.exists():
                self.assertEqual(stat.read_text().split(") ", 1)[1].split()[0], "Z")


if __name__ == "__main__":
    unittest.main()
