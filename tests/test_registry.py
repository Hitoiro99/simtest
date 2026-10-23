import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from platform_support.io import read_yaml
from solvers import registry
from solvers.base import SolverAdapter
from solvers.exceptions import ConfigurationError, VersionMismatchError
from solvers.models import SolverInfo


class RegistryAdapter(SolverAdapter):
    """部署协议测试替身，不代表项目已接入新的求解器。"""

    name = "RegistryTest"
    version = "legacy"
    main_executable = "testSolver"

    @staticmethod
    def version_key(version):
        return {"legacy": 1, "current": 2}[version]

    def probe(self, context):
        environment = context.environment
        return SolverInfo(
            self.name, environment["TEST_VERSION"], "test-build", "test", [],
            {self.main_executable: environment["TEST_EXECUTABLE"]},
        )

    def validate(self, context):
        raise NotImplementedError

    def preprocess(self, context):
        raise NotImplementedError

    def build(self, context):
        raise NotImplementedError

    def postprocess(self, context):
        raise NotImplementedError


class BranchAlpha(RegistryAdapter):
    name = "BranchTest"
    branch = "Alpha"
    version = "1"

    @staticmethod
    def version_key(version):
        return int(version)

    def probe(self, context):
        environment = context.environment
        return SolverInfo(
            self.name, environment["TEST_VERSION"], "test-build", self.branch, [],
            {self.main_executable: environment["TEST_EXECUTABLE"]},
        )


class BranchBeta(BranchAlpha):
    branch = "Beta"
    version = "2506"


class RegistryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        adapters = {RegistryAdapter.name: {RegistryAdapter.version: RegistryAdapter}}
        self.registry_patch = patch.dict(registry.ADAPTERS, adapters, clear=True)
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)
        discovery = patch.object(registry, "discover", return_value=registry.ADAPTERS)
        discovery.start()
        self.addCleanup(discovery.stop)

    def installation(self, version):
        path = self.root / version
        binary = path / "bin" / RegistryAdapter.main_executable
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("controlled executable path", encoding="utf-8")
        return {
            "solver": RegistryAdapter.name,
            "version": version,
            "path": str(path),
            "environment": {"kind": "existing"},
        }

    def arguments(self, installation, version=None):
        if version is None:
            version = installation["version"]
        return SimpleNamespace(
            solver=RegistryAdapter.name, version=version, path=installation["path"], config=None,
            environment="existing", environment_script=None, environment_module=[], force=False,
        )

    def environment(self, installation):
        return {
            "TEST_VERSION": installation["version"],
            "TEST_EXECUTABLE": str(Path(installation["path"]) / "bin" / RegistryAdapter.main_executable),
        }

    def write_config(self, installations):
        file = self.root / "config.yaml"
        file.write_text(yaml.safe_dump({"installations": installations}), encoding="utf-8")
        return file

    def test_register_and_select_non_openfoam_installation(self):
        installation = self.installation("legacy")
        with patch.dict(os.environ, self.environment(installation)):
            registered = registry.register_install(self.root, self.arguments(installation))
            selected, environment, info, adapter = registry.select_install(self.root, "RegistryTest@legacy")
        self.assertEqual(Path(registered["config"]), self.root / "config.yaml")
        self.assertEqual(selected, installation)
        self.assertEqual(info.version, "legacy")
        self.assertEqual(set(info.executables), {"testSolver"})
        self.assertIsInstance(adapter, RegistryAdapter)
        self.assertEqual(environment["TEST_VERSION"], "legacy")
        self.assertEqual(read_yaml(self.root / "config.yaml")["installations"], [installation])
        self.assertIn("config.yaml", (self.root / ".gitignore").read_text().splitlines())

    def test_version_mismatch_does_not_replace_existing_configuration(self):
        installation = self.installation("legacy")
        file = self.write_config([installation])
        ignore = self.root / ".gitignore"
        ignore.write_text("user-owned-entry\n", encoding="utf-8")
        original = file.read_bytes()
        with patch.dict(os.environ, self.environment(installation)):
            with self.assertRaises(VersionMismatchError):
                registry.register_install(self.root, self.arguments(installation, version="current"))
        self.assertEqual(file.read_bytes(), original)
        self.assertEqual(ignore.read_text(), "user-owned-entry\n")

    def test_selection_rejects_changed_actual_version(self):
        installation = self.installation("legacy")
        file = self.write_config([installation])
        original = file.read_bytes()
        environment = self.environment(installation)
        environment["TEST_VERSION"] = "current"
        with patch.dict(os.environ, environment), self.assertRaises(VersionMismatchError):
            registry.select_install(self.root, "RegistryTest@legacy")
        self.assertEqual(file.read_bytes(), original)

    def test_missing_or_foreign_main_program_is_rejected(self):
        installation = self.installation("legacy")
        other = self.installation("current")
        adapter = RegistryAdapter()
        info = adapter.probe(SimpleNamespace(environment=self.environment(other)))
        with self.assertRaises(VersionMismatchError):
            adapter.check_installation(info, installation["path"])
        info.executables = {}
        with self.assertRaises(VersionMismatchError):
            adapter.check_installation(info, installation["path"])

        environment = self.environment(installation)
        environment["TEST_EXECUTABLE"] = self.environment(other)["TEST_EXECUTABLE"]
        with patch.dict(os.environ, environment):
            with self.assertRaises(ConfigurationError):
                registry.register_install(self.root, self.arguments(installation))
            self.assertFalse((self.root / "config.yaml").exists())
            self.write_config([installation])
            with self.assertRaises(VersionMismatchError):
                registry.select_install(self.root, "RegistryTest@legacy")

    def test_latest_and_archive_sorting_use_kernel_version_rules(self):
        legacy = self.installation("legacy")
        current = self.installation("current")
        self.write_config([legacy, current])
        with patch.object(registry, "load_env", side_effect=self.environment):
            selected, _, info, adapter = registry.select_install(self.root, "RegistryTest@latest")
        self.assertEqual(selected, current)
        self.assertEqual(info.version, "current")
        self.assertEqual(adapter.version, "legacy")

        (self.root / "config.yaml").unlink()
        with patch.object(RegistryAdapter, "probe", side_effect=AssertionError("unexpected installation probe")):
            latest = max(["legacy", "current"], key=lambda version: registry.version_key("RegistryTest", version))
        self.assertEqual(latest, "current")

    def test_cross_branch_latest_is_ambiguous_but_explicit_version_selects(self):
        alpha = self.installation("1")
        alpha["branch"] = "Alpha"
        alpha["solver"] = "BranchTest"
        beta = self.installation("2506")
        beta["branch"] = "Beta"
        beta["solver"] = "BranchTest"
        self.write_config([alpha, beta])

        def environment(installation):
            return {
                "TEST_VERSION": installation["version"],
                "TEST_BRANCH": installation["branch"],
                "TEST_EXECUTABLE": str(Path(installation["path"]) / "bin" / RegistryAdapter.main_executable),
            }

        with patch.dict(registry.ADAPTERS, {"BranchTest": {"1": BranchAlpha, "2506": BranchBeta}}, clear=True), \
                patch.object(registry, "load_env", side_effect=environment):
            with self.assertRaises(ConfigurationError):
                registry.select_install(self.root, "BranchTest@latest")
            selected, _, info, adapter = registry.select_install(self.root, "BranchTest@2506")
        self.assertEqual(selected["branch"], "Beta")
        self.assertEqual(info.branch, "Beta")
        self.assertIsInstance(adapter, BranchBeta)

    def test_path_prepend_is_applied_to_activated_environment(self):
        environment = registry.load_env(
            {"environment": {"kind": "existing"}, "path_prepend": ["/opt/paraview"]}
        )
        self.assertTrue(environment["PATH"].startswith("/opt/paraview" + os.pathsep))
        with self.assertRaises(ConfigurationError):
            registry.load_env({"environment": {"kind": "existing"}, "path_prepend": "bad"})

    def test_environment_modes_remain_exclusive_and_existing_is_independent(self):
        for spec in (
            {"kind": "existing", "script": "not-used"},
            {"kind": "existing", "modules": ["test"]},
            {"kind": "script", "script": "not-used", "modules": ["test"]},
            {"kind": "module", "modules": ["test"], "script": "not-used"},
        ):
            with self.subTest(spec=spec), patch.object(registry.subprocess, "run") as execute:
                with self.assertRaises(ConfigurationError):
                    registry.load_env({"environment": spec})
                execute.assert_not_called()
        with patch.dict(os.environ, {"REGISTRY_TEST_MARKER": "original"}):
            environment = registry.load_env({"environment": {"kind": "existing"}})
            environment["REGISTRY_TEST_MARKER"] = "changed"
            self.assertEqual(os.environ["REGISTRY_TEST_MARKER"], "original")


if __name__ == "__main__":
    unittest.main()
