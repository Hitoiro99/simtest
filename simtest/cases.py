from __future__ import annotations

import math
import re
from pathlib import Path

from solvers.exceptions import ConfigurationError
from .expression import evaluate, validate_expression
from .io import identifier, read_yaml, sha256, within
from .units import convert, parse


def mapping(value, label):
    if not isinstance(value, dict): raise ConfigurationError(label + " 必须为字典")
    return value


def typed(value, declaration):
    kind = declaration.get("type")
    if kind == "real":
        if type(value) not in (int, float) or not math.isfinite(value): raise ConfigurationError("real 必须是有限实数")
        return float(value)
    if kind == "integer":
        if type(value) is not int: raise ConfigurationError("integer 不能截断或转换布尔值")
    elif kind == "boolean":
        if type(value) is not bool: raise ConfigurationError("boolean 必须为布尔值")
    elif kind in ("string", "path"):
        if not isinstance(value, str): raise ConfigurationError(kind + " 必须为字符串")
    else: raise ConfigurationError("不支持的数据类型: %r" % kind)
    return value


def execution_config(execution):
    execution = dict(mapping(execution, "execution"))
    backend = execution.get("backend", "serial")
    processes = execution.get("processes", 1)
    threads = execution.get("openmp_threads", 1)
    if backend not in ("serial", "openmp", "cuda"): raise ConfigurationError("未知 execution.backend")
    if type(processes) is not int or processes < 1: raise ConfigurationError("processes 必须为正整数")
    if type(threads) is not int or threads < 1: raise ConfigurationError("openmp_threads 必须为正整数")
    if backend == "serial" and threads > 1: raise ConfigurationError("serial 不允许多个 OpenMP 线程")
    if backend == "openmp" and "openmp_threads" not in execution: raise ConfigurationError("openmp 必须指定 openmp_threads")
    execution.update(backend=backend, processes=processes, openmp_threads=threads)
    return execution


def load_case(path):
    path = Path(path).resolve()
    case = read_yaml(path / "case.yaml")
    identifier(case.get("id"))
    if case["id"] != path.name: raise ConfigurationError("案例 id 与目录名不一致")
    if "mesh" in case: raise ConfigurationError("case.yaml 不允许 mesh 字段")
    if not isinstance(case.get("version"), str): raise ConfigurationError("案例 version 必须为字符串")
    namespace = set()
    for section in ("constants", "variables", "derived_variables", "monitors", "fields"):
        entries = mapping(case.get(section, {}), section)
        for name, declaration in entries.items():
            identifier(name); mapping(declaration, name)
            if declaration.get("type") not in ("real", "integer", "boolean", "string", "path"):
                raise ConfigurationError("未知类型: " + name)
            parse(declaration.get("unit"))
            if section in ("constants", "variables", "derived_variables"):
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",name): raise ConfigurationError("物理变量名必须为表达式标识符")
                if name in namespace or name in ("execution", "solver", "condition", "pi"):
                    raise ConfigurationError("变量命名空间冲突: " + name)
                namespace.add(name)
            if section == "variables" and "value" in declaration:
                raise ConfigurationError("变量值只能放在工况 values: " + name)
            if section == "constants": typed(declaration.get("value"), declaration)
            if section in ("monitors", "fields"):
                maps = declaration.get("mapping", [])
                if not isinstance(maps, list): raise ConfigurationError("mapping 必须为列表")
                for item in maps:
                    mapping(item, "mapping item")
                    if not isinstance(item.get("solver"), str) or not isinstance(item.get("name"), str):
                        raise ConfigurationError("mapping 缺少 solver/name")
                    parse(item.get("unit", declaration.get("unit")))
    execution_config(case.get("execution", {}))
    mesh_asset(path)
    return case


def mesh_asset(path):
    assets = [Path(path)/name for name in ("mesh.cgns", "mesh.msh", "polyMesh") if (Path(path)/name).exists()]
    if len(assets) != 1: raise ConfigurationError("案例必须有且只有一个源网格资产")
    asset = assets[0]
    if asset.name == "polyMesh":
        if not asset.is_dir(): raise ConfigurationError("polyMesh 必须为目录")
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            if not (asset/name).is_file(): raise ConfigurationError("网格缺少 " + name)
    elif not asset.is_file(): raise ConfigurationError("网格资产必须为文件")
    return asset


def load_condition(path, case, condition_id):
    identifier(condition_id)
    file = within(path, Path(path)/"conditions"/(condition_id+".yaml"))
    condition = read_yaml(file)
    values = mapping(condition.get("values", {}), "values")
    declared = case.get("variables", {})
    if set(values)-set(declared): raise ConfigurationError("工况含未声明变量或试图覆盖常量/派生变量: " + ",".join(set(values)-set(declared)))
    resolved, chain = {}, []
    for name, declaration in case.get("constants", {}).items():
        resolved[name] = typed(declaration["value"], declaration)
        chain.append({"name":name,"kind":"constant","value":resolved[name],"unit":declaration.get("unit", "")})
    for name, declaration in declared.items():
        if name not in values:
            if declaration.get("required", False): raise ConfigurationError("缺少必填变量: " + name)
            continue
        item = mapping(values[name], name)
        if "value" not in item: raise ConfigurationError("变量缺少 value: " + name)
        value = typed(item["value"], declaration)
        if declaration["type"] in ("real", "integer"):
            value = convert(value, item.get("unit", declaration.get("unit")), declaration.get("unit"))
            if declaration["type"] == "integer":
                if not value.is_integer(): raise ConfigurationError("单位换算后的整数不是整数")
                value = int(value)
        resolved[name] = value
        chain.append({"name":name,"kind":"variable","input":item,"value":value,"unit":declaration.get("unit", "")})
    pending = dict(case.get("derived_variables", {}))
    while pending:
        progress = False
        for name, declaration in list(pending.items()):
            try: value = evaluate(declaration["expression"], resolved)
            except ConfigurationError as exc:
                if str(exc).startswith("未知表达式参数:"): continue
                raise
            resolved[name] = typed(value, declaration)
            chain.append({"name":name,"kind":"derived","expression":declaration["expression"],"value":value,"unit":declaration.get("unit", "")})
            del pending[name]; progress = True
        if not progress: raise ConfigurationError("派生变量循环或引用未定义变量: " + ",".join(pending))
    references = mapping(condition.get("references", {}), "references")
    for ref_id, reference in references.items():
        identifier(ref_id); mapping(reference, ref_id)
        if reference.get("kind") not in ("analytical", "experimental"): raise ConfigurationError("未知 reference.kind")
        if "source" not in reference: raise ConfigurationError("reference 必须包含 source；其内容不做校验")
        targets = [key for key in ("monitor", "field") if key in reference]
        if len(targets) != 1: raise ConfigurationError("reference 必须恰好指定 monitor 或 field")
        target = targets[0]; group = "monitors" if target == "monitor" else "fields"
        if reference[target] not in case.get(group, {}): raise ConfigurationError("reference 引用未知注册项")
        unit = case[group][reference[target]].get("unit", "")
        scale = mapping(reference.get("reference_scale"), "reference_scale")
        if convert(scale.get("value"), scale.get("unit", unit), unit) <= 0: raise ConfigurationError("reference_scale 必须为正且有限")
        if target == "monitor":
            convert(reference.get("value"), reference.get("unit", unit), unit)
        else:
            if reference["kind"] != "analytical": raise ConfigurationError("首期场参考仅支持 analytical，不能用不一致网格编号比较实验场")
            identifier(reference.get("domain"))
            if "time" in reference or "times" in reference: raise ConfigurationError("场 reference 不配置比较时刻")
            expressions = reference.get("expression")
            if isinstance(expressions, dict) and set(expressions) != {"x", "y", "z"}:
                raise ConfigurationError("矢量 expression 必须有 x/y/z 全部分量")
            if not isinstance(expressions, (str, dict)): raise ConfigurationError("非法解析场 expression")
            params = mapping(reference.get("parameters", {}), "parameters")
            env = {"x":0., "y":.01, "z":0., "t":0.}
            for name, item in params.items():
                identifier(name)
                if name in env or name == "pi": raise ConfigurationError("参考参数覆盖坐标/时间/pi")
                mapping(item, "parameter")
                scale_value, _ = parse(item.get("unit"))
                env[name] = convert(item.get("value"), item.get("unit"), item.get("unit"))*scale_value
            for expr in expressions.values() if isinstance(expressions, dict) else [expressions]: validate_expression(expr, env)
    condition["_provenance"] = {"file":str(file),"sha256":sha256(file),"resolution_chain":chain}
    return condition, resolved


def discover_cases(root):
    return sorted(p.parent for p in (Path(root)/"cases").glob("*/case.yaml"))


def discover_conditions(path):
    return sorted(p.stem for p in (Path(path)/"conditions").glob("*.yaml"))
