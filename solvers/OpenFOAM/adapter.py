from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from case_management.cases import mesh_asset
from run_control.environment import find_tool, run_capture
from common.io import atomic_json, inventory, within
from case_management.templates import materialize
from . import __name__ as _package_name
from solvers.base import SolverAdapter, supervise
from solvers.exceptions import (
    ConfigurationError,
    MeshConversionError,
    MissingOutputError,
    PreprocessError,
    UnsupportedCaseError,
    UnsupportedResultFormatError,
)
from solvers.models import Command, SolverInfo, StageResult
from solvers.registry import register_adapter


@register_adapter
class OpenFOAMAdapter(SolverAdapter):
    name = "OpenFOAM"
    version = "12"
    capabilities = frozenset({"transient", "steady", "incompressible", "laminar", "mpi", "serial"})

    @staticmethod
    def version_key(version):
        if not re.fullmatch(r"[1-9][0-9]*", str(version)):
            raise UnsupportedCaseError("首期 Foundation 版本序列只接受整数版本；不能与 OpenCFD vYYMM 混排")
        return int(version)

    def probe(self, context):
        env = context.environment
        tools = {
            name: find_tool(name, env)
            for name in (
                "icoFoam",
                "foamDictionary",
                "checkMesh",
                "decomposePar",
                "reconstructPar",
                "foamToVTK",
                "foamPostProcess",
                "pvpython",
            )
        }
        help_text = run_capture([tools["icoFoam"], "-help"], env)
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
        return SolverInfo(self.name, version, build.group(1), "Foundation", capabilities, tools)

    def validate(self, context):
        from solvers.registry import mapped

        for section in ("monitors", "fields"):
            for name, declaration in getattr(context, "case", {}).get(section, {}).items():
                mapped(declaration, name, self)
        if context.execution["backend"] != "serial":
            raise UnsupportedCaseError("当前 Foundation/icoFoam Adapter 不支持请求的 OpenMP/CUDA 后端")
        if context.execution["processes"] > 1 and "mpi" not in context.info.capabilities:
            raise UnsupportedCaseError("MPI 请求无法满足")
        if context.execution["processes"] > (os.cpu_count() or 1):
            raise UnsupportedCaseError("MPI 进程数超过本机可用逻辑 CPU")
        asset = mesh_asset(context.case_path)
        if asset.name != "polyMesh":
            raise MeshConversionError(
                "AICFD-NewPre 未安装/未配置；不能转换 %s。首期可使用 polyMesh 源网格。" % asset.name, stage="preprocess"
            )

    def command(self, context, argv, timeout=None):
        if context.work.exists():
            location = context.work
        else:
            location = context.input
        return Command(argv, location, context.environment, timeout or context.timeout, context.heartbeat_timeout)

    def native(self, context, tool, args, label, case_path=None):
        location = case_path or context.work
        argv = [
            context.info.executables.get(tool) or find_tool(tool, context.environment),
            "-case",
            str(location),
        ] + list(args)
        result = supervise(
            Command(argv, location, context.environment, context.timeout, context.heartbeat_timeout),
            context.run_dir / "logs" / (label + ".log"),
        )
        context.manifest.setdefault("preparation_commands", []).append(result.diagnostics)
        output = (context.run_dir / "logs" / (label + ".log")).read_text(encoding="utf-8", errors="replace")
        if "FOAM FATAL" in output:
            raise PreprocessError("原生工具报告 FATAL 错误: " + label)
        return result

    def dictionary(self, context, path, entry=None, keywords=False):
        argv = [context.info.executables["foamDictionary"], path.name]
        if entry:
            argv += ["-entry", entry]
        if keywords:
            argv += ["-keywords"]
        elif entry:
            argv += ["-value"]
        else:
            argv += []
        return run_capture(argv, context.environment, cwd=path.parent)

    def preprocess(self, context):
        self.validate(context)
        materialize(context, self)
        source = mesh_asset(context.case_path)
        source_hash = inventory(source)
        target = context.input / "constant" / "polyMesh"
        shutil.copytree(source, target)
        if inventory(target) != source_hash:
            raise PreprocessError("网格复制哈希不一致")
        context.manifest["mesh"] = {"mode": "copy", "source": str(source), "sha256": source_hash}
        # Instantiate the mesh and fields through the native utility. writeObjects
        # writes the expanded initial field so the frozen snapshot contains numbers.
        if any("#codeStream" in p.read_text(encoding="utf-8") for p in (context.input / "0").glob("*") if p.is_file()):
            self.native(
                context,
                "foamPostProcess",
                ["-func", "writeObjects(U)", "-fields", "(U)", "-time", "0"],
                "initialize",
                context.input,
            )
        for file in (context.input / "0").glob("*"):
            if file.is_file() and "#codeStream" in file.read_text():
                raise PreprocessError("原生初始化未展开初始场")
        required = [context.input / "system" / name for name in ("controlDict", "fvSchemes", "fvSolution")]
        required += list((context.input / "0").glob("*")) + list((context.input / "constant").glob("*"))
        for file in required:
            if file.is_file():
                self.dictionary(context, file)
        boundary = (context.input / "constant" / "polyMesh" / "boundary").read_text(encoding="utf-8")
        # Native boundary is a list, not a dictionary. Extract its declared names.
        boundary_list = re.search(r"(?m)^\s*(\d+)\s*\n\s*\(", boundary)
        if not boundary_list:
            raise PreprocessError("无法识别原生边界列表")
        patch_names = re.findall(r"(?m)^\s*([A-Za-z_][\w.-]*)\s*\n\s*\{", boundary[boundary_list.end() :])
        if len(patch_names) != int(boundary_list.group(1)):
            raise PreprocessError("边界列表计数不符")
        if len(patch_names) != len(set(patch_names)) or not patch_names:
            raise PreprocessError("网格边界名称不唯一或不可解析")
        for file in (context.input / "0").glob("*"):
            if not file.is_file():
                continue
            text = self.dictionary(context, file, "boundaryField", keywords=True)
            field_names = [
                line.strip() for line in text.splitlines() if re.fullmatch(r"[A-Za-z_][\w.-]*", line.strip())
            ]
            if set(field_names) != set(patch_names) or len(field_names) != len(patch_names):
                raise PreprocessError("初始场与网格边界必须恰好匹配: " + file.name)
        self.native(context, "checkMesh", [], "checkMesh", context.input)
        if "Mesh OK" not in (context.run_dir / "logs" / "checkMesh.log").read_text():
            raise PreprocessError("checkMesh 未确认 Mesh OK")
        application = (
            self.dictionary(context, context.input / "system" / "controlDict", "application").strip().rstrip(";")
        )
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", application):
            raise PreprocessError("非法 application")
        context.manifest["application"] = application
        context.info.executables[application] = find_tool(application, context.environment)
        source_snapshot = context.input / "_source"
        source_snapshot.mkdir()
        shutil.copy2(context.case_path / "case.yaml", source_snapshot / "case.yaml")
        shutil.copy2(
            context.case_path / "conditions" / (context.condition_id + ".yaml"), source_snapshot / "condition.yaml"
        )
        if (context.case_path / "references").exists():
            shutil.copytree(context.case_path / "references", source_snapshot / "references")
        shutil.copytree(context.case_path / "templates", source_snapshot / "templates")
        generated = within(context.input, context.input / "dynamicCode")
        if generated.exists():
            shutil.rmtree(generated)
        context.manifest["input_sha256"] = inventory(context.input)
        for file in context.input.rglob("*"):
            if file.is_file():
                file.chmod(0o444)
        shutil.copytree(context.input, context.work)
        for file in context.work.rglob("*"):
            if file.is_file():
                file.chmod(0o644)
        if context.execution["processes"] > 1:
            self.native(context, "decomposePar", [], "decomposePar")
        return StageResult(artifacts=[str(context.input)], diagnostics={"mesh_patches": patch_names})

    def build(self, context):
        app = context.info.executables[context.manifest["application"]]
        argv = [app, "-case", str(context.work)]
        if context.execution["processes"] > 1:
            argv = (
                [context.info.executables["mpirun"], "-np", str(context.execution["processes"])] + argv + ["-parallel"]
            )
        return self.command(context, argv)

    def postprocess(self, context):
        from .monitors import normalize_monitors
        from .fields import normalize_fields

        if context.execution["processes"] > 1:
            self.native(context, "reconstructPar", [], "reconstructPar")
        records, diagnostics = normalize_monitors(context, self)
        context.diagnostics.extend(diagnostics)
        context.manifest["monitors"] = {
            key: [{"step": r.step, "time": r.time, "value": r.value, "quality": r.quality} for r in value]
            for key, value in records.items()
        }
        fields = normalize_fields(context, self)
        return StageResult(artifacts=[str(context.normalized)], warnings=diagnostics, diagnostics={"fields": fields})
