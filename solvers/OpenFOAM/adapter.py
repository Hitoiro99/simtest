from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
from pathlib import Path

from case_management.cases import mesh_asset
from platform_support.io import atomic_json, inventory, within
from platform_support.units import factor
from case_management.templates import choose, materialize, template_files
from . import __name__ as _package_name
from solvers.base import SolverAdapter, find_tool, run_capture, supervise
from solvers.exceptions import (
    CancelledError,
    ConfigurationError,
    FieldParseError,
    MeshConversionError,
    MissingOutputError,
    MonitorParseError,
    PreprocessError,
    SolverTimeoutError,
    UnsupportedCaseError,
    UnsupportedResultFormatError,
)
from solvers.models import Command, MonitorRecord, StageResult
from solvers.registry import mapped


class OpenFOAMAdapter(SolverAdapter):
    """OpenFOAM 内核公共行为；具体版本与分支由 versions/ 子类提供。"""

    name = "OpenFOAM"
    branch = ""
    main_executable = "icoFoam"
    post_process_tool = "foamPostProcess"
    supported_applications = ("icoFoam", "simpleFoam")
    environment_keys = ("WM_PROJECT_VERSION", "WM_PROJECT_DIR", "WM_OPTIONS", "OMP_NUM_THREADS")
    capabilities = frozenset({"transient", "steady", "incompressible", "laminar", "mpi", "serial"})
    identity_code_files = (Path(__file__).with_name("vtk_bridge.py"),)

    def validate(self, context):
        from solvers.registry import mapped

        for section in ("monitors", "fields"):
            for name, declaration in getattr(context, "case", {}).get(section, {}).items():
                mapped(declaration, name, self)
        if context.execution["backend"] != "serial":
            raise UnsupportedCaseError("当前 OpenFOAM Adapter 不支持请求的 OpenMP/CUDA 后端")
        if context.execution["processes"] > 1 and "mpi" not in context.info.capabilities:
            raise UnsupportedCaseError("MPI 请求无法满足")
        if context.execution["processes"] > (os.cpu_count() or 1):
            raise UnsupportedCaseError("MPI 进程数超过本机可用逻辑 CPU")
        self.validate_mesh(mesh_asset(context.case_path))

    def validate_mesh(self, asset):
        """检查当前内核支持的源网格及 polyMesh 必需文件，不启动原生工具。"""
        if asset.name != "polyMesh":
            raise MeshConversionError(
                "AICFD-NewPre 未安装/未配置；不能转换 %s。首期可使用 polyMesh 源网格。" % asset.name, stage="preprocess"
            )

        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            if not (asset / name).is_file():
                raise ConfigurationError("网格缺少 " + name)

    def validate_template(self, path):
        """检查 OpenFOAM 原生模板布局；版本类可重载，不解析案例物理参数。"""
        if path.parts[0] not in ("0", "constant", "system"):
            raise ConfigurationError("OpenFOAM 原生模板文件须位于 0/constant/system")

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
        environment = dict(context.environment)
        environment["PWD"] = str(path.parent)
        return run_capture(argv, environment, cwd=path.parent)

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
                self.post_process_tool,
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
        if application not in self.supported_applications:
            raise UnsupportedCaseError("不支持的求解器主程序: " + application)
        expected = getattr(context.info, "application", "")
        if expected and application != expected:
            raise UnsupportedCaseError("controlDict 的 application 与探测结果不一致: " + application)
        context.manifest["application"] = application
        context.info.executables[application] = find_tool(application, context.environment)
        source_snapshot = context.input / "_source"
        source_snapshot.mkdir()
        shutil.copy2(context.case_path / "case.yaml", source_snapshot / "case.yaml")
        shutil.copy2(
            context.case_path / "conditions" / (context.condition_id + ".yaml"), source_snapshot / "condition.yaml"
        )
        chain = choose(context.case_path, self)
        for entry in chain:
            target = source_snapshot / "templates" / "definitions" / (entry["id"] + ".yaml")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry["_path"] / "template.yaml", target)
        for relative, file in template_files(chain, self).items():
            target = within(source_snapshot, source_snapshot / "templates" / "effective" / relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
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
            for link in sorted(context.work.rglob("*")):
                if not link.is_symlink():
                    continue
                target = within(context.work, link.resolve(strict=True))
                if target.is_dir():
                    inventory(target)
                    link.unlink()
                    shutil.copytree(target, link)
                elif target.is_file():
                    link.unlink()
                    shutil.copy2(target, link)
                else:
                    raise PreprocessError("分区工作区链接目标不是普通文件或目录")
        return StageResult(artifacts=[str(context.input)], diagnostics={"mesh_patches": patch_names})

    def build(self, context):
        app = context.info.executables[context.manifest["application"]]
        argv = [app, "-case", str(context.work)]
        if context.execution["processes"] > 1:
            argv = (
                [context.info.executables["mpirun"], "-np", str(context.execution["processes"])] + argv + ["-parallel"]
            )
        return self.command(context, argv)

    def read_log(self, path):
        """读取完整原生日志时间轴和残差，保留坏行诊断；缺少时间轴时抛出 MissingOutputError。"""
        text = path.read_text(encoding="utf-8", errors="replace")
        current = None
        axis = []
        residuals = {}
        warnings = []
        for line_no, line in enumerate(text.splitlines(), 1):
            match = re.match(r"^Time = (\S+)\s*$", line)
            if match:
                token = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(s|ms)?", match.group(1))
                if not token:
                    raise MonitorParseError("未知日志时间单位/格式")
                try:
                    time_value = float(token.group(1)) * (0.001 if token.group(2) == "ms" else 1)
                except ValueError:
                    raise MonitorParseError("非法原生物理时间")
                if not math.isfinite(time_value):
                    raise MonitorParseError("非有限物理时间")
                if axis and time_value <= axis[-1]:
                    raise MonitorParseError("原生时间轴重复或倒序")
                axis.append(time_value)
                current = (len(axis), time_value)
            match = re.search(r"Solving for (\w+), Initial residual = (\S+),", line)
            if match and current:
                try:
                    value = float(match.group(2))
                except ValueError:
                    warnings.append({"kind": "bad_line", "file": str(path), "line": line_no})
                    continue
                name = "residual:" + match.group(1)
                # One initial residual per equation/time step, first linear solve.
                residuals.setdefault(name, {}).setdefault(current, value)
        if not axis:
            raise MissingOutputError("日志中没有迭代/时间记录")
        return axis, residuals, warnings

    def read_tables(self, work):
        """读取 function-object 表格并展开向量；结构、时间或重复记录异常时抛出 MonitorParseError。"""
        tables = {}
        warnings = []
        for file in sorted((work / "postProcessing").rglob("*.dat")):
            header = None
            for number, line in enumerate(file.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if not line.strip():
                    continue
                if line.lstrip().startswith("#"):
                    candidate = line.lstrip("# \t").split()
                    if candidate and candidate[0] == "Time":
                        header = candidate
                    continue
                if header is None:
                    raise MonitorParseError("数据行之前缺少 Time 表头: " + str(file))
                tokens = re.findall(r"\([^)]*\)|\S+", line)
                if len(tokens) != len(header):
                    warnings.append({"kind": "bad_line", "file": str(file), "line": number, "reason": "列数与表头不一致"})
                try:
                    time_value = float(tokens[0])
                    if not math.isfinite(time_value):
                        raise ValueError("nonfinite time")
                except (ValueError, IndexError):
                    # Without an axis, the record cannot be placed. Fail explicitly
                    # instead of making an earlier valid record look like the last.
                    raise MonitorParseError("监控记录的时间不可解析: %s:%s" % (file, number))
                parsed = []
                for index, name in enumerate(header[1:], 1):
                    token = tokens[index] if index < len(tokens) else "nan"
                    try:
                        values = [float(v) for v in token.strip("()").split()]
                    except ValueError:
                        values = [float("nan")]
                        warnings.append(
                            {
                                "kind": "invalid",
                                "native_monitor": name,
                                "time": time_value,
                                "file": str(file),
                                "line": number,
                                "reason": "不可解析的监控值",
                            }
                        )
                    if len(values) == 1:
                        parsed.append((name, values[0]))
                    elif len(values) == 3:
                        parsed.extend((name + "." + c, v) for c, v in zip("xyz", values))
                    else:
                        raise MonitorParseError("监控列结构未知: " + name)
                for name, value in parsed:
                    values = tables.setdefault(name, {})
                    if time_value in values:
                        raise MonitorParseError("重复监控记录/多个冲突来源: " + name)
                    values[time_value] = value
        return tables, warnings

    def read_monitors(self, context):
        """按案例映射和单位标准化全部监控记录，写入 CSV 并返回记录与警告。"""
        axis, residuals, warnings = self.read_log(context.run_dir / "logs" / "solver.log")
        tables, table_warnings = self.read_tables(context.work)
        warnings += table_warnings
        step_by_time = {value: index + 1 for index, value in enumerate(axis)}
        start = float(
            self.dictionary(context, context.input / "system" / "controlDict", "startTime").strip().rstrip(";")
        )
        step_by_time[start] = 0
        records = {}
        for name, declaration in context.case.get("monitors", {}).items():
            native, unit = mapped(declaration, name, self)
            conversion = factor(unit, declaration.get("unit", ""))
            data = []
            if native.startswith("residual:"):
                if native not in residuals:
                    raise MissingOutputError("缺少必需残差: " + native)
                pairs = [(step, time, value) for (step, time), value in residuals[native].items()]
            else:
                if native not in tables:
                    raise MissingOutputError("缺少必需 function-object 监控: " + native)
                pairs = []
                for time, value in tables[native].items():
                    if time not in step_by_time:
                        raise MonitorParseError("监控时间未能与求解器原生时间轴对应: " + str(time))
                    pairs.append((step_by_time[time], time, value))
            for step, time, value in sorted(pairs):
                value *= conversion
                quality = "valid" if math.isfinite(value) else "invalid"
                data.append(MonitorRecord(name, step, time, value, declaration.get("unit", ""), quality))
                if quality == "invalid":
                    warnings.append({"kind": "invalid", "monitor": name, "step": step, "time": time, "reason": "NaN/Inf"})
            if not data:
                raise MissingOutputError("必需监控没有记录: " + name)
            records[name] = data
        if not records:
            raise MissingOutputError("案例未登记任何可读取监控项")
        aligned = {}
        for name, data in records.items():
            for record in data:
                aligned.setdefault((record.step, record.time), {})[name] = record.value
        context.normalized.mkdir(parents=True, exist_ok=True)
        with (context.normalized / "monitors.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["step", "time"] + list(records))
            for (step, time), row in sorted(aligned.items()):
                writer.writerow([step, time] + [row.get(name, "") for name in records])
        monitor_mapping = {}
        for name, declaration in context.case.get("monitors", {}).items():
            mapping = {"native": mapped(declaration, name, self)[0], "unit": declaration.get("unit", "")}
            if mapped(declaration, name, self)[0].startswith("residual:"):
                mapping["kind"] = "residual"
            else:
                mapping["kind"] = "monitor"
            monitor_mapping[name] = mapping
        context.manifest["monitor_mapping"] = monitor_mapping
        context.manifest["solver_time_axis"] = {"start": start, "steps": axis}
        return records, warnings

    def output_times(self, context):
        """校验原生时间元数据与日志步号，返回全部输出时刻及来源。"""
        axis = context.manifest["solver_time_axis"]
        start = axis["start"]
        result = []
        for directory in sorted(context.work.iterdir()):
            if not directory.is_dir() or not re.fullmatch(r"[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?", directory.name):
                continue
            metadata = directory / "uniform" / "time"
            if metadata.is_file():
                # index provides an exact relationship to the logged step, without
                # introducing a physical-time matching tolerance. value retains
                # the full precision written by the solver, unlike its display name.
                self.dictionary(context, metadata)
                raw = metadata.read_text(encoding="utf-8")
                value_match = re.search(r"(?m)^\s*value\s+([^;]+);", raw)
                index_match = re.search(r"(?m)^\s*index\s+(\d+)\s*;", raw)
                if not value_match or not index_match:
                    raise FieldParseError("time 字典缺少 value/index")
                time_value = float(value_match.group(1))
                step = int(index_match.group(1))
                if step == 0:
                    if time_value != start or float(directory.name) != start:
                        raise FieldParseError("原生初始时间与 startTime 不符")
                elif step > len(axis["steps"]) or axis["steps"][step - 1] != float(directory.name):
                    raise FieldParseError(
                        "原生时间 index/name 未与求解器日志轴对应: index=%s name=%s" % (step, directory.name)
                    )
                label = self.dictionary(context, metadata, "name").strip().strip('";')
                if label != directory.name:
                    raise FieldParseError("原生 time.name 与目录不符")
                provenance = {
                    "kind": "native_time_dictionary",
                    "file": str(metadata),
                    "step": step,
                    "raw_value": value_match.group(1),
                }
            elif float(directory.name) == start:
                time_value = start
                provenance = {"kind": "native_controlDict_startTime", "file": str(context.input / "system" / "controlDict")}
            else:
                raise MissingOutputError("场输出缺少物理时间元数据: " + str(directory))
            if not math.isfinite(time_value):
                raise FieldParseError("非有限物理时间")
            result.append(
                {"name": directory.name, "time": time_value, "reader_time": float(directory.name), "provenance": provenance}
            )
        result.sort(key=lambda entry: entry["time"])
        if not result or len({e["time"] for e in result}) != len(result):
            raise FieldParseError("场时间轴空或重复")
        return result

    def read_fields(self, context):
        """读取所需域和场的全部时刻；保留原生直读、导出回退与标准 VTU 校验。"""
        from solvers.base import supervise
        from solvers.models import Command

        references = [r for r in context.condition.get("references", {}).values() if "field" in r]
        if not references:
            return []
        times = self.output_times(context)
        specs = {}
        for reference in references:
            canonical = reference["field"]
            declaration = context.case["fields"][canonical]
            native, unit = mapped(declaration, canonical, self)
            key = (canonical, reference["domain"])
            spec = {
                "canonical": canonical,
                "native": native,
                "unit": declaration.get("unit", ""),
                "factor": factor(unit, declaration.get("unit", "")),
                "domain": reference["domain"],
                "components": 3 if isinstance(reference["expression"], dict) else 1,
            }
            if key in specs and spec != specs[key]:
                raise FieldParseError("同一场 reference 的维度结构矛盾")
            specs[key] = spec
            for entry in times:
                domain_path = context.work / entry["name"]
                if reference["domain"] != "internalMesh":
                    parts = reference["domain"].split("/")
                    if len(parts) != 2 or parts[-1] != "internalMesh":
                        raise UnsupportedResultFormatError("场域应对应原生内部网格/region/internalMesh")
                    domain_path /= parts[0]
                if not (domain_path / native).is_file():
                    raise MissingOutputError("输出时刻缺少验证场: %s/%s" % (entry["name"], native))
        if len({s["canonical"] for s in specs.values()}) != len(specs):
            raise UnsupportedResultFormatError("首期同一场跨多个域的 VTU 文件命名尚未实现，不能覆盖文件")
        bridge = Path(__file__).resolve().with_name("vtk_bridge.py")
        request_file = context.work / "field-request.json"
        response_file = context.work / "field-response.json"
        request = {
            "mode": "native",
            "case": str(context.work),
            "times": times,
            "fields": list(specs.values()),
            "output": str(context.normalized / "fields"),
            "response": str(response_file),
        }
        atomic_json(request_file, request)
        argv = [context.info.executables["pvpython"], "--force-offscreen-rendering", str(bridge), str(request_file)]
        try:
            result = supervise(
                Command(argv, context.work, context.environment, context.timeout, context.heartbeat_timeout),
                context.run_dir / "logs" / "field-reader.log",
            )
            mode = "native"
        except (CancelledError, SolverTimeoutError):
            raise
        except Exception as exc:
            # The fallback is explicit and logged. It cannot convert a missing field into success.
            context.diagnostics.append(
                {"kind": "reader_fallback", "reason": str(exc), "from": "OpenFOAMReader", "to": "foamToVTK"}
            )
            self.native(
                context,
                "foamToVTK",
                [
                    "-ascii",
                    "-noPointValues",
                    "-noFaceZones",
                    "-noFunctionObjects",
                    "-useTimeName",
                    "-fields",
                    "(" + " ".join(sorted({s["native"] for s in specs.values()})) + ")",
                ],
                "field-export",
            )
            request["mode"] = "exchange"
            atomic_json(request_file, request)
            try:
                result = supervise(
                    Command(argv, context.work, context.environment, context.timeout, context.heartbeat_timeout),
                    context.run_dir / "logs" / "exchange-reader.log",
                )
            except Exception as fallback:
                raise UnsupportedResultFormatError("原生直读和导出回退均失败: " + str(fallback))
            mode = "exchange"
        if not response_file.is_file():
            raise MissingOutputError("读取器没有返回场数据")
        response = json.loads(response_file.read_text())
        expected = {(s["canonical"], s["domain"], t["time"]) for s in specs.values() for t in times}
        actual = {(d["field"], d["domain"], d["time"]) for d in response["datasets"]}
        if actual != expected or len(response["datasets"]) != len(expected):
            raise MissingOutputError("标准场未完整覆盖域/物理量/全部时刻")
        # PVD physical time comes from verified native metadata, never filename parsing.
        entries = ['<?xml version="1.0"?>', '<VTKFile type="Collection" version="0.1"><Collection>']
        for dataset in response["datasets"]:
            entries.append(
                '<DataSet timestep="%s" group="%s" part="0" file="%s"/>'
                % (format(dataset["time"], ".17g"), dataset["field"], Path(dataset["file"]).name)
            )
        entries.append("</Collection></VTKFile>")
        (context.normalized / "fields" / "fields.pvd").write_text("\n".join(entries) + "\n")
        context.manifest["field_reader"] = {
            "mode": mode,
            "vtk_version": response["vtk_version"],
            "command": result.diagnostics,
            "times": times,
        }
        context.manifest["fields"] = [{k: v for k, v in d.items() if k != "samples"} for d in response["datasets"]]
        return response["datasets"]

    def postprocess(self, context):
        if context.execution["processes"] > 1:
            self.native(context, "reconstructPar", [], "reconstructPar")
        records, diagnostics = self.read_monitors(context)
        context.diagnostics.extend(diagnostics)
        context.manifest["monitors"] = {
            key: [{"step": r.step, "time": r.time, "value": r.value, "quality": r.quality} for r in value]
            for key, value in records.items()
        }
        fields = self.read_fields(context)
        return StageResult(artifacts=[str(context.normalized)], warnings=diagnostics, diagnostics={"fields": fields})
