import json
import math
import re
from pathlib import Path

from solvers.exceptions import CancelledError, FieldParseError, MissingOutputError, SolverTimeoutError, UnsupportedResultFormatError
from solvers.registry import mapped
from simtest.io import atomic_json
from simtest.units import factor


def output_times(context,adapter):
    axis = context.manifest["solver_time_axis"]
    start = axis["start"]
    result = []
    for directory in sorted(context.work.iterdir()):
        if not directory.is_dir() or not re.fullmatch(r"[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?",directory.name): continue
        metadata = directory/"uniform"/"time"
        if metadata.is_file():
            # index provides an exact relationship to the logged step, without
            # introducing a physical-time matching tolerance. value retains
            # the full precision written by the solver, unlike its display name.
            adapter.dictionary(context,metadata)
            raw = metadata.read_text(encoding="utf-8")
            value_match = re.search(r"(?m)^\s*value\s+([^;]+);",raw)
            index_match = re.search(r"(?m)^\s*index\s+(\d+)\s*;",raw)
            if not value_match or not index_match: raise FieldParseError("time 字典缺少 value/index")
            time_value = float(value_match.group(1)); step = int(index_match.group(1))
            if step == 0:
                if time_value != start or float(directory.name) != start: raise FieldParseError("原生初始时间与 startTime 不符")
            elif step > len(axis["steps"]) or axis["steps"][step-1] != float(directory.name):
                raise FieldParseError("原生时间 index/name 未与求解器日志轴对应: index=%s name=%s" % (step,directory.name))
            label = adapter.dictionary(context,metadata,"name").strip().strip('";')
            if label != directory.name: raise FieldParseError("原生 time.name 与目录不符")
            provenance = {"kind":"native_time_dictionary","file":str(metadata),"step":step,"raw_value":value_match.group(1)}
        elif float(directory.name) == start:
            time_value = start
            provenance = {"kind":"native_controlDict_startTime","file":str(context.input/"system"/"controlDict")}
        else: raise MissingOutputError("场输出缺少物理时间元数据: " + str(directory))
        if not math.isfinite(time_value): raise FieldParseError("非有限物理时间")
        result.append({"name":directory.name,"time":time_value,"reader_time":float(directory.name),"provenance":provenance})
    result.sort(key=lambda entry:entry["time"])
    if not result or len({e["time"] for e in result}) != len(result): raise FieldParseError("场时间轴空或重复")
    return result


def normalize_fields(context,adapter):
    from solvers.base import supervise
    from solvers.models import Command
    references = [r for r in context.condition.get("references",{}).values() if "field" in r]
    if not references: return []
    times = output_times(context,adapter)
    specs = {}
    for reference in references:
        canonical = reference["field"]; declaration = context.case["fields"][canonical]
        native,unit = mapped(declaration,canonical,adapter)
        key = (canonical,reference["domain"])
        spec = {"canonical":canonical,"native":native,"unit":declaration.get("unit",""),
                "factor":factor(unit,declaration.get("unit","")),"domain":reference["domain"],
                "components":3 if isinstance(reference["expression"],dict) else 1}
        if key in specs and spec != specs[key]: raise FieldParseError("同一场 reference 的维度结构矛盾")
        specs[key] = spec
        for entry in times:
            domain_path = context.work/entry["name"]
            if reference["domain"] != "internalMesh":
                parts = reference["domain"].split("/")
                if len(parts) != 2 or parts[-1] != "internalMesh": raise UnsupportedResultFormatError("场域应对应原生内部网格/region/internalMesh")
                domain_path /= parts[0]
            if not (domain_path/native).is_file(): raise MissingOutputError("输出时刻缺少验证场: %s/%s" % (entry["name"],native))
    if len({s["canonical"] for s in specs.values()}) != len(specs):
        raise UnsupportedResultFormatError("首期同一场跨多个域的 VTU 文件命名尚未实现，不能覆盖文件")
    bridge = Path(__file__).resolve().parents[2]/"simtest"/"vtk_bridge.py"
    request_file = context.work/"field-request.json"; response_file = context.work/"field-response.json"
    request = {"mode":"native","case":str(context.work),"times":times,"fields":list(specs.values()),
               "output":str(context.normalized/"fields"),"response":str(response_file)}
    atomic_json(request_file,request)
    argv = [context.info.executables["pvpython"],"--force-offscreen-rendering",str(bridge),str(request_file)]
    try:
        result = supervise(Command(argv,context.work,context.environment,context.timeout,context.heartbeat_timeout),context.run_dir/"logs"/"field-reader.log")
        mode = "native"
    except (CancelledError,SolverTimeoutError):
        raise
    except Exception as exc:
        # The fallback is explicit and logged. It cannot convert a missing field into success.
        context.diagnostics.append({"kind":"reader_fallback","reason":str(exc),"from":"OpenFOAMReader","to":"foamToVTK"})
        adapter.native(context,"foamToVTK",["-ascii","-noPointValues","-noFaceZones","-noFunctionObjects","-useTimeName","-fields","("+" ".join(sorted({s["native"] for s in specs.values()}))+")"],"field-export")
        request["mode"] = "exchange"; atomic_json(request_file,request)
        try:
            result = supervise(Command(argv,context.work,context.environment,context.timeout,context.heartbeat_timeout),context.run_dir/"logs"/"exchange-reader.log")
        except Exception as fallback:
            raise UnsupportedResultFormatError("原生直读和导出回退均失败: " + str(fallback))
        mode = "exchange"
    if not response_file.is_file(): raise MissingOutputError("读取器没有返回场数据")
    response = json.loads(response_file.read_text())
    expected = {(s["canonical"],s["domain"],t["time"]) for s in specs.values() for t in times}
    actual = {(d["field"],d["domain"],d["time"]) for d in response["datasets"]}
    if actual != expected or len(response["datasets"]) != len(expected): raise MissingOutputError("标准场未完整覆盖域/物理量/全部时刻")
    # PVD physical time comes from verified native metadata, never filename parsing.
    entries = ['<?xml version="1.0"?>','<VTKFile type="Collection" version="0.1"><Collection>']
    for dataset in response["datasets"]:
        entries.append('<DataSet timestep="%s" group="%s" part="0" file="%s"/>' % (format(dataset["time"],".17g"),dataset["field"],Path(dataset["file"]).name))
    entries.append('</Collection></VTKFile>')
    (context.normalized/"fields"/"fields.pvd").write_text("\n".join(entries)+"\n")
    context.manifest["field_reader"] = {"mode":mode,"vtk_version":response["vtk_version"],"command":result.diagnostics,"times":times}
    context.manifest["fields"] = [{k:v for k,v in d.items() if k != "samples"} for d in response["datasets"]]
    return response["datasets"]
