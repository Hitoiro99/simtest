"""Explicit one-time mesh preparation. Never called implicitly by a test run."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from simtest.environment import activate, executable
from simtest.io import atomic_json, inventory, sha256
from solvers.base import supervise
from solvers.models import Command


def main():
    root = Path(__file__).resolve().parents[3]
    case = root/"cases"/"shear-decay-2d"
    definition = Path(__file__).resolve().with_name("blockMeshDict")
    if (case/"polyMesh").exists(): raise SystemExit("polyMesh 已存在，不覆盖受控源网格")
    build = root/".build"/"mesh"
    if build.exists(): raise SystemExit(".build/mesh 已存在，请先审查之前制备的日志")
    (build/"system").mkdir(parents=True)
    shutil.copy2(definition, build/"system"/"blockMeshDict")
    (build/"system"/"controlDict").write_text("FoamFile { format ascii; class dictionary; object controlDict; }\napplication icoFoam; startFrom startTime; startTime 0; stopAt endTime; endTime 1; deltaT 0.001; writeControl timeStep; writeInterval 100;\n")
    env = activate({"environment":{"kind":"script","script":"/opt/openfoam12/etc/bashrc"}})
    records = []
    for name in ("blockMesh", "checkMesh"):
        result = supervise(Command([executable(name, env), "-case", str(build)], build, env), build/(name+".log"))
        records.append(result.diagnostics)
    log = (build/"checkMesh.log").read_text()
    if "Mesh OK" not in log: raise SystemExit("checkMesh 未确认 Mesh OK")
    shutil.copytree(build/"constant"/"polyMesh", case/"polyMesh")
    provenance = case/"mesh-provenance"
    provenance.mkdir()
    for name in ("blockMesh.log", "checkMesh.log"): shutil.copy2(build/name, provenance/name)
    atomic_json(provenance/"manifest.json", {"commands":records,"definition_sha256":sha256(definition),
                "mesh_sha256":inventory(case/"polyMesh"),"generator":"OpenFOAM Foundation 12 blockMesh"})
    print(json.dumps({"mesh":str(case/"polyMesh"),"files":len(inventory(case/"polyMesh"))}))


if __name__ == "__main__": main()
