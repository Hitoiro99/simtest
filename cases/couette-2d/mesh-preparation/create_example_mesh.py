"""Explicit one-time mesh preparation. Never called implicitly by a test run."""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from common.io import atomic_json, inventory, sha256
from solvers.base import find_tool, supervise
from solvers.models import Command
from solvers.registry import load_env


def main():
    root = Path(__file__).resolve().parents[3]
    case = root / "cases" / "couette-2d"
    definition = Path(__file__).resolve().with_name("blockMeshDict")
    if (case / "polyMesh").exists():
        raise SystemExit("polyMesh 已存在，不覆盖受控源网格")
    build = root / ".build" / "mesh"
    if build.exists():
        raise SystemExit(".build/mesh 已存在，请先审查之前制备的日志")
    (build / "system").mkdir(parents=True)
    shutil.copy2(definition, build / "system" / "blockMeshDict")
    (build / "system" / "controlDict").write_text(
        "FoamFile { format ascii; class dictionary; object controlDict; }\n"
        "application icoFoam; startFrom startTime; startTime 0; stopAt endTime; "
        "endTime 10; deltaT 0.01; writeControl timeStep; writeInterval 100;\n",
        encoding="utf-8",
    )
    env = load_env({"environment": {"kind": "script", "script": "/opt/openfoam12/etc/bashrc"}})
    records = []
    for name in ("blockMesh", "checkMesh"):
        result = supervise(Command([find_tool(name, env), "-case", str(build)], build, env), build / (name + ".log"))
        records.append(result.diagnostics)
    log = (build / "checkMesh.log").read_text(encoding="utf-8")
    if "Mesh OK" not in log:
        raise SystemExit("checkMesh 未确认 Mesh OK")
    shutil.copytree(build / "constant" / "polyMesh", case / "polyMesh")
    provenance = case / "mesh-provenance"
    provenance.mkdir()
    for name in ("blockMesh.log", "checkMesh.log"):
        shutil.copy2(build / name, provenance / name)
    atomic_json(
        provenance / "manifest.json",
        {
            "case": "couette-2d",
            "commands": records,
            "definition_sha256": sha256(definition),
            "geometry_m": {"length": 1.0, "gap": 1.0, "depth": 0.01},
            "cells": {"x": 16, "y": 32, "z": 1},
            "mesh_sha256": inventory(case / "polyMesh"),
            "generator": "OpenFOAM Foundation 12 blockMesh",
        },
    )
    try:
        shutil.rmtree(build)
    except OSError as exc:
        print("警告: 无法清理 .build/mesh: %s" % exc, file=sys.stderr)
    else:
        try:
            build.parent.rmdir()
        except OSError:
            pass
    print(json.dumps({"mesh": str(case / "polyMesh"), "files": len(inventory(case / "polyMesh"))}))


if __name__ == "__main__":
    main()
