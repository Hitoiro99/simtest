from __future__ import annotations

import re
import shutil
from pathlib import Path

from solvers.base import find_tool, run_capture
from solvers.exceptions import ConfigurationError, UnsupportedCaseError
from solvers.models import SolverInfo
from solvers.registry import register_adapter

from ..adapter import OpenFOAMAdapter


@register_adapter
class V12(OpenFOAMAdapter):
    """OpenFOAM Foundation 12 的具体行为。"""

    version = "12"
    branch = "Foundation"
    version_rule = "Foundation integer release; same branch only"

    @staticmethod
    def version_key(version):
        if not re.fullmatch(r"[1-9][0-9]*", str(version)):
            raise UnsupportedCaseError("Foundation 版本序列只接受整数版本；不能与 OpenCFD vYYMM 混排")
        return int(version)

    def probe(self, context):
        env = context.environment
        tools = {self.main_executable: find_tool(self.main_executable, env)}
        for name in (
            "foamDictionary",
            "checkMesh",
            "decomposePar",
            "reconstructPar",
            "foamToVTK",
            "foamPostProcess",
            "pvpython",
        ):
            tools[name] = find_tool(name, env)
        help_text = run_capture([tools[self.main_executable], "-help"], env)
        match = re.search(r"^Using:\s*OpenFOAM-([0-9]+)\s*\(see https?://openfoam.org\)", help_text, re.M)
        if not match:
            raise UnsupportedCaseError("无法从求解器可执行文件确认 Foundation 版本")
        version = match.group(1)
        build = re.search(r"^Build:\s*(\S+)", help_text, re.M)
        if not build:
            raise ConfigurationError("求解器未提供构建标识")
        mpi = shutil.which("mpirun", path=env.get("PATH"))
        if mpi:
            tools["mpirun"] = str(Path(mpi).resolve())
        if mpi:
            capabilities = sorted(self.capabilities)
        else:
            capabilities = sorted(self.capabilities - {"mpi"})
        return SolverInfo(self.name, version, build.group(1), self.branch, capabilities, tools)
