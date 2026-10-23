import re
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from case_management.cases import execution_configs, load_case, load_condition
from case_management.templates import materialize
from platform_support.expression import evaluate
from solvers.OpenFOAM.versions.v12 import V12
from solvers.OpenFOAM.versions.v2506 import V2506


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "cases" / "couette-2d"


def patch_block(text, name):
    match = re.search(r"\b" + re.escape(name) + r"\s*\{(.*?)\}", text, re.S)
    if match is None:
        raise AssertionError("缺少边界: " + name)
    return match.group(1)


class CouetteCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_case(CASE_PATH)
        cls.condition, cls.parameters = load_condition(CASE_PATH, cls.case, "Re=10")

    def test_case_and_condition_define_the_approved_physics(self):
        self.assertEqual(self.case["id"], "couette-2d")
        self.assertEqual(self.parameters["wall_gap"], 0.01)
        self.assertEqual(self.parameters["wall_velocity"], 1.0)
        self.assertEqual(self.parameters["kinematic_viscosity"], 0.001)
        self.assertEqual(self.parameters["reynolds_number"], 10.0)
        self.assertEqual(self.parameters["start_iteration"], 0)
        self.assertEqual(self.parameters["end_iteration"], 200)
        self.assertEqual(self.parameters["iteration_step"], 1)
        self.assertEqual(self.parameters["write_interval"], 20)

        references = self.condition["references"]
        self.assertEqual(references["analytical_velocity"]["field"], "velocity")
        self.assertEqual(references["analytical_pressure"]["field"], "pressure")
        for reference in references.values():
            source = CASE_PATH / reference["source"]["file"]
            self.assertTrue(source.is_file(), source)

    def test_steady_couette_expression_at_internal_points(self):
        reference = self.condition["references"]["analytical_velocity"]
        expression = reference["expression"]["x"]
        parameters = {name: item["value"] for name, item in reference["parameters"].items()}

        def velocity(y):
            return evaluate(expression, {**parameters, "x": 0.0, "y": y, "z": 0.0, "t": 0.0})

        self.assertAlmostEqual(velocity(0.0), 0.0)
        self.assertAlmostEqual(velocity(0.005), 0.5)
        self.assertAlmostEqual(velocity(0.01), 1.0)
        self.assertEqual(reference["expression"]["y"], "0")
        self.assertEqual(reference["expression"]["z"], "0")

    def test_openfoam_template_has_couette_boundaries_and_iteration_controls(self):
        adapter = V12()
        with tempfile.TemporaryDirectory() as temp:
            input_path = Path(temp) / "input"
            context = SimpleNamespace(
                case_path=CASE_PATH,
                input=input_path,
                parameters=self.parameters,
                execution=execution_configs(self.case["execution"])[0],
                info=SimpleNamespace(name="OpenFOAM", version="12"),
                condition_id="Re=10",
                manifest={},
            )
            materialize(context, adapter)

            velocity = (input_path / "0" / "U").read_text(encoding="utf-8")
            pressure = (input_path / "0" / "p").read_text(encoding="utf-8")
            controls = (input_path / "system" / "controlDict").read_text(encoding="utf-8")

        self.assertIn("internalField uniform (0 0 0);", velocity)
        self.assertEqual(velocity.count("value nonuniform List<vector>"), 2)
        expected_velocity = {
            "inlet_lowerFluid": "fixedValue",
            "outlet_lowerFluid": "zeroGradient",
            "bottomWall": "fixedValue",
            "movingWall": "fixedValue",
            "inlet_upperFluid": "fixedValue",
            "outlet_upperFluid": "zeroGradient",
            "frontAndBack_lowerFluid": "empty",
            "frontAndBack_upperFluid": "empty",
        }
        for name, kind in expected_velocity.items():
            self.assertIn("type " + kind + ";", patch_block(velocity, name), name)

        expected_pressure = {
            "inlet_lowerFluid": "zeroGradient",
            "outlet_lowerFluid": "fixedValue",
            "bottomWall": "zeroGradient",
            "movingWall": "zeroGradient",
            "inlet_upperFluid": "zeroGradient",
            "outlet_upperFluid": "fixedValue",
            "frontAndBack_lowerFluid": "empty",
            "frontAndBack_upperFluid": "empty",
        }
        for name, kind in expected_pressure.items():
            self.assertIn("type " + kind + ";", patch_block(pressure, name), name)

        self.assertRegex(controls, r"(?m)^application\s+simpleFoam;$")
        self.assertRegex(controls, r"(?m)^startTime\s+0;$")
        self.assertRegex(controls, r"(?m)^endTime\s+200;$")
        self.assertRegex(controls, r"(?m)^deltaT\s+1;$")
        self.assertRegex(controls, r"(?m)^writeInterval\s+20;$")

    def test_v2506_template_extends_foundation_files(self):
        adapter = V2506()
        with tempfile.TemporaryDirectory() as temp:
            input_path = Path(temp) / "input"
            context = SimpleNamespace(
                case_path=CASE_PATH,
                input=input_path,
                parameters=self.parameters,
                execution=execution_configs(self.case["execution"])[0],
                info=SimpleNamespace(name="OpenFOAM", version="2506"),
                condition_id="Re=10",
                manifest={},
            )
            materialize(context, adapter)
            velocity = (input_path / "0" / "U").read_text(encoding="utf-8")
            controls = (input_path / "system" / "controlDict").read_text(encoding="utf-8")
            transport = (input_path / "constant" / "transportProperties").read_text(encoding="utf-8")
            turbulence = (input_path / "constant" / "turbulenceProperties").read_text(encoding="utf-8")
        self.assertEqual(context.manifest["template"]["id"], "openfoam-opencfd-2506")
        self.assertEqual(context.manifest["template"]["chain"], ["openfoam-foundation-12", "openfoam-opencfd-2506"])
        self.assertRegex(controls, r"(?m)^application\s+simpleFoam;$")
        self.assertIn("movingWall", velocity)
        self.assertIn("transportModel  Newtonian;", transport)
        self.assertIn("simulationType  laminar;", turbulence)

    def test_mesh_definition_has_one_source_and_expected_patches(self):
        self.assertTrue((CASE_PATH / "polyMesh").is_dir())
        self.assertFalse((CASE_PATH / "mesh.cgns").exists())
        self.assertFalse((CASE_PATH / "mesh.msh").exists())

        definition = (CASE_PATH / "mesh-preparation" / "blockMeshDict").read_text(encoding="utf-8")
        self.assertEqual(definition.count("(120 8 1)"), 2)
        expected = {
            "inlet_lowerFluid": "patch",
            "inlet_upperFluid": "patch",
            "outlet_lowerFluid": "patch",
            "outlet_upperFluid": "patch",
            "bottomWall": "wall",
            "movingWall": "wall",
            "frontAndBack_lowerFluid": "empty",
            "frontAndBack_upperFluid": "empty",
        }
        for name, kind in expected.items():
            self.assertRegex(definition, r"\b" + name + r"\s*\{\s*type " + kind + r";")


if __name__ == "__main__":
    unittest.main()
