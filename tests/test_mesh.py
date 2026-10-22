import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "cases" / "couette-2d" / "mesh-preparation" / "create_example_mesh.py"
)


def load_script():
    spec = importlib.util.spec_from_file_location("create_example_mesh_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def layout(root):
    location = root / "work" / "a" / "b" / "create_example_mesh.py"
    location.parent.mkdir(parents=True)
    location.write_text("", encoding="utf-8")
    (location.parent / "blockMeshDict").write_text("blockMeshDict", encoding="utf-8")
    (root / "cases" / "couette-2d").mkdir(parents=True)
    return location


class MeshPreparationTests(unittest.TestCase):
    def prepare(self, module, root, mesh_ok=True):
        def fake_supervise(command, log):
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("Mesh OK\n" if mesh_ok else "Mesh FAILED\n", encoding="utf-8")
            poly = log.parent / "constant" / "polyMesh"
            poly.mkdir(parents=True, exist_ok=True)
            (poly / "points").write_text("points", encoding="utf-8")
            return SimpleNamespace(diagnostics={})

        with patch.object(module, "supervise", fake_supervise), patch.object(
            module, "load_env", lambda *args, **kwargs: {}
        ), patch.object(module, "find_tool", lambda *args, **kwargs: "tool"):
            return module.main()

    def test_success_removes_build_and_writes_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module = load_script()
            module.__file__ = str(layout(root))
            self.prepare(module, root)
            self.assertFalse((root / ".build").exists())
            self.assertTrue((root / "cases" / "couette-2d" / "polyMesh" / "points").is_file())
            self.assertTrue(
                (root / "cases" / "couette-2d" / "mesh-provenance" / "manifest.json").is_file()
            )

    def test_checkmesh_failure_keeps_build_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module = load_script()
            module.__file__ = str(layout(root))
            with self.assertRaises(SystemExit):
                self.prepare(module, root, mesh_ok=False)
            self.assertTrue((root / ".build" / "mesh" / "checkMesh.log").is_file())
            self.assertFalse((root / "cases" / "couette-2d" / "polyMesh").exists())
