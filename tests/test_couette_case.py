from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from case_management.cases import execution_configs, load_case, load_condition
from case_management.templates import materialize
from common.expression import evaluate
from solvers.OpenFOAM.adapter import OpenFOAMAdapter


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "cases" / "couette-2d"


class CouetteCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_case(CASE_PATH)
        cls.condition, cls.parameters = load_condition(CASE_PATH, cls.case, "Re=10")

    def test_case_and_condition_define_the_approved_physics(self):
        self.assertEqual(self.case["id"], "couette-2d")
        self.assertEqual(self.parameters["wall_gap"], 1.0)
        self.assertEqual(self.parameters["wall_velocity"], 1.0)
        self.assertEqual(self.parameters["kinematic_viscosity"], 0.1)
        self.assertEqual(self.parameters["reynolds_number"], 10.0)
        self.assertEqual(self.parameters["start_time"], 0.0)
        self.assertEqual(self.parameters["end_time"], 10.0)
        self.assertEqual(self.parameters["time_step"], 0.01)
        self.assertEqual(self.parameters["write_interval"], 100)
        self.assertEqual(self.parameters["output_interval"], 1.0)

        references = self.condition["references"]
        self.assertEqual(references["analytical_velocity"]["field"], "velocity")
        self.assertEqual(references["analytical_pressure"]["field"], "pressure")
        for reference in references.values():
            source = CASE_PATH / reference["source"]["file"]
            self.assertTrue(source.is_file(), source)

    def test_startup_couette_expression_at_saved_times(self):
        reference = self.condition["references"]["analytical_velocity"]
        expression = reference["expression"]["x"]
        parameters = {name: item["value"] for name, item in reference["parameters"].items()}

        def velocity(y, time):
            return evaluate(expression, {**parameters, "x": 0.0, "y": y, "z": 0.0, "t": time})

        self.assertAlmostEqual(velocity(0.5, 0.0), 0.0)
        self.assertAlmostEqual(velocity(0.0, 1.0), 0.0)
        self.assertAlmostEqual(velocity(1.0, 1.0), 1.0)
        self.assertAlmostEqual(velocity(0.25, 10.0), 0.25, places=4)
        self.assertAlmostEqual(velocity(0.75, 10.0), 0.75, places=4)
        self.assertEqual(reference["expression"]["y"], "0")
        self.assertEqual(reference["expression"]["z"], "0")

    def test_openfoam_template_has_couette_boundaries_and_time_controls(self):
        adapter = OpenFOAMAdapter()
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
        self.assertIn("upperWall { type fixedValue; value uniform (1.0 0 0); }", velocity)
        self.assertIn("lowerWall { type fixedValue; value uniform (0 0 0); }", velocity)
        self.assertIn("left { type cyclic; }", velocity)
        self.assertIn("right { type cyclic; }", velocity)
        self.assertIn("frontAndBack { type empty; }", velocity)
        self.assertIn("lowerWall { type zeroGradient; }", pressure)
        self.assertIn("upperWall { type zeroGradient; }", pressure)
        self.assertIn("startTime 0.0;", controls)
        self.assertIn("endTime 10.0;", controls)
        self.assertIn("deltaT 0.01;", controls)
        self.assertIn("writeInterval 100;", controls)

    def test_mesh_definition_has_one_source_and_expected_patches(self):
        self.assertTrue((CASE_PATH / "polyMesh").is_dir())
        self.assertFalse((CASE_PATH / "mesh.cgns").exists())
        self.assertFalse((CASE_PATH / "mesh.msh").exists())

        definition = (CASE_PATH / "mesh-preparation" / "blockMeshDict").read_text(encoding="utf-8")
        self.assertIn("(16 32 1)", definition)
        self.assertIn("left { type cyclic; neighbourPatch right;", definition)
        self.assertIn("right { type cyclic; neighbourPatch left;", definition)
        self.assertIn("lowerWall { type wall;", definition)
        self.assertIn("upperWall { type wall;", definition)
        self.assertIn("frontAndBack { type empty;", definition)


if __name__ == "__main__":
    unittest.main()
