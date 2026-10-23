from __future__ import annotations

import re
import shutil
from pathlib import Path

from solvers.base import find_tool, run_capture
from solvers.exceptions import UnsupportedCaseError
from solvers.models import SolverInfo
from solvers.registry import register_adapter

from ..adapter import OpenFOAMAdapter


@register_adapter
class V2506(OpenFOAMAdapter):
    """OpenCFD OpenFOAM v2506 的具体行为。"""

    version = "2506"
    branch = "OpenCFD"
    post_process_tool = "postProcess"
    version_rule = "OpenCFD vYYMM release; same branch only"

    @staticmethod
    def version_key(version):
        if not re.fullmatch(r"[0-9]{4}", str(version)):
            raise UnsupportedCaseError("OpenCFD 版本序列只接受四位 YYMM 版本")
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
            "postProcess",
            "pvpython",
        ):
            tools[name] = find_tool(name, env)
        help_text = run_capture([tools[self.main_executable], "-help"], env)
        match = re.search(r"OpenFOAM-([0-9]{4})", help_text)
        if not match:
            raise UnsupportedCaseError("无法从求解器可执行文件确认 OpenCFD 版本")
        version = match.group(1)
        build = re.search(r"(?m)^Build:\s*(\S+)", help_text)
        build_id = build.group(1) if build else "unknown"
        mpi = shutil.which("mpirun", path=env.get("PATH"))
        if mpi:
            tools["mpirun"] = str(Path(mpi).resolve())
        if mpi:
            capabilities = sorted(self.capabilities)
        else:
            capabilities = sorted(self.capabilities - {"mpi"})
        return SolverInfo(self.name, version, build_id, self.branch, capabilities, tools)
