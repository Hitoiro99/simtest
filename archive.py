"""标准结果独立回读、不可变归档与经双重校验后的工作区清理。"""

import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from platform_support.io import atomic_json, identifier, inventory, json_safe, within
from solvers.exceptions import ConfigurationError, PostprocessError


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise PostprocessError("标准结果包含非有限坐标、时间或几何值")
    return number


def _arrays(parent):
    if parent is None:
        raise PostprocessError("VTU 缺少必需数据节点")
    result = {}
    for array in parent:
        name = array.get("Name")
        if not name or name in result or array.get("format") != "ascii":
            raise PostprocessError("VTU 数组名称重复、缺失或非 ASCII")
        result[name] = array
    return result


def _xml(path):
    text = Path(path).read_text(encoding="utf-8")
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise PostprocessError("标准 XML 不允许 DTD 或实体声明")
    return ET.fromstring(text)


def _numbers(array, count, components=1, integer=False):
    if array is None or int(array.get("NumberOfComponents", "1")) != components:
        raise PostprocessError("VTU 数组分量不符")
    if array.get("type") not in {"Float32", "Float64", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64"}:
        raise PostprocessError("VTU 数值数组类型无效")
    if integer:
        values = [int(value) for value in (array.text or "").split()]
    else:
        values = [float(value) for value in (array.text or "").split()]
    if len(values) != count * components:
        raise PostprocessError("VTU 数组长度与网格计数不符")
    return values


def _string(array):
    if array is None or array.get("type") != "String" or array.get("NumberOfTuples") != "1":
        raise PostprocessError("VTU 字符串元数据缺失")
    values = [int(value) for value in (array.text or "").split()]
    if not values or values[-1] != 0 or 0 in values[:-1]:
        raise PostprocessError("VTU 字符串元数据损坏")
    return bytes(values[:-1]).decode("utf-8")


def _same_value(actual, expected):
    if math.isnan(actual) and math.isnan(expected):
        return True
    if actual == expected:
        return True
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-14)


def _read_vtu(path, entry, reference, declaration):
    """只依赖标准 XML 读取规范 ASCII VTU，不使用清单中的 samples 或比较结果。"""
    tree = _xml(path)
    if tree.tag != "VTKFile" or tree.get("type") != "UnstructuredGrid":
        raise PostprocessError("不是标准 UnstructuredGrid VTU")
    grid = tree.find("UnstructuredGrid")
    pieces = grid.findall("Piece") if grid is not None else []
    if len(pieces) != 1:
        raise PostprocessError("VTU 必须含一个明确网格 Piece")
    piece = pieces[0]
    cells, points = int(piece.get("NumberOfCells", "0")), int(piece.get("NumberOfPoints", "0"))
    if cells <= 0 or points <= 0 or cells != entry["cells"] or points != entry["points"]:
        raise PostprocessError("VTU 网格计数与清单不一致")
    coordinates = piece.find("Points")
    if coordinates is None or len(coordinates) != 1:
        raise PostprocessError("VTU 缺少唯一坐标数组")
    point_array = coordinates[0]
    if point_array.get("format") != "ascii":
        raise PostprocessError("VTU 坐标数组必须为 ASCII")
    for value in _numbers(point_array, points, 3):
        _finite(value)
    topology = _arrays(piece.find("Cells"))
    if not {"connectivity", "offsets", "types"}.issubset(topology):
        raise PostprocessError("VTU 拓扑数组缺失")
    offsets = _numbers(topology["offsets"], cells, integer=True)
    types = _numbers(topology["types"], cells, integer=True)
    if any(right <= left for left, right in zip([0] + offsets, offsets)):
        raise PostprocessError("VTU 单元偏移不递增")
    connectivity = _numbers(topology["connectivity"], offsets[-1], integer=True)
    if any(index < 0 or index >= points for index in connectivity) or any(kind <= 0 or kind > 81 for kind in types):
        raise PostprocessError("VTU 拓扑索引或单元类型无效")
    fixed_counts = {1: 1, 3: 2, 5: 3, 8: 4, 9: 4, 10: 4, 11: 8, 12: 8, 13: 6, 14: 5}
    for index, kind in enumerate(types):
        start = offsets[index - 1] if index else 0
        if kind in fixed_counts and offsets[index] - start != fixed_counts[kind]:
            raise PostprocessError("VTU 单元类型与点数不符")
    if 42 in types:
        faces = topology.get("faces")
        face_offsets = topology.get("faceoffsets")
        if faces is None or face_offsets is None:
            raise PostprocessError("VTU 多面体缺少面拓扑")
        boundaries = _numbers(face_offsets, cells, integer=True)
        face_values = [int(value) for value in (faces.text or "").split()]
        cursor = 0
        for index, kind in enumerate(types):
            if kind != 42:
                if boundaries[index] != -1:
                    raise PostprocessError("非多面体单元包含多面体偏移")
                continue
            if cursor >= len(face_values):
                raise PostprocessError("VTU 多面体面拓扑缺失")
            number_of_faces = face_values[cursor]
            cursor += 1
            if number_of_faces < 4:
                raise PostprocessError("VTU 多面体面数无效")
            start = offsets[index - 1] if index else 0
            vertices = set(connectivity[start:offsets[index]])
            found = set()
            for _ in range(number_of_faces):
                if cursor >= len(face_values):
                    raise PostprocessError("VTU 多面体面点数缺失")
                count = face_values[cursor]
                cursor += 1
                face = face_values[cursor:cursor + count]
                if count < 3 or len(face) != count or len(set(face)) != count or not set(face).issubset(vertices):
                    raise PostprocessError("VTU 多面体面点索引无效")
                cursor += count
                found.update(face)
            if cursor != boundaries[index] or found != vertices:
                raise PostprocessError("VTU 多面体面偏移或顶点覆盖无效")
        if cursor != len(face_values):
            raise PostprocessError("VTU 多面体有多余面拓扑")
    metadata = _arrays(grid.find("FieldData"))
    physical_time = _finite(_numbers(metadata.get("physical_time"), 1)[0])
    field = entry["field"]
    unit = declaration.get("unit", "")
    if physical_time != float(entry["time"]) or _string(metadata.get("domain")) != entry["domain"]:
        raise PostprocessError("VTU 物理时间或域与清单不符")
    if _string(metadata.get("unit")) != unit or entry["unit"] != unit:
        raise PostprocessError("VTU 字段单位不符")
    if _string(metadata.get("coordinate_unit")) != "m" or _string(metadata.get("time_unit")) != "s":
        raise PostprocessError("VTU 坐标和时间单位必须为 m/s")
    vector = isinstance(reference["expression"], dict)
    components = 3 if vector else 1
    expected = {field, "cell_center", "cell_volume", "original_cell_id"}
    if vector:
        expected.update(field + "_" + component for component in ("x", "y", "z", "magnitude"))
    arrays = _arrays(piece.find("CellData"))
    if set(arrays) != expected or set(entry["arrays"]) != expected:
        raise PostprocessError("VTU 缺少验证场分量或包含未声明物理场")
    if len(piece.find("PointData") or []):
        raise PostprocessError("标准验证 VTU 不保存额外点字段")
    values = _numbers(arrays[field], cells, components)
    centers = _numbers(arrays["cell_center"], cells, 3)
    volumes = _numbers(arrays["cell_volume"], cells)
    ids = _numbers(arrays["original_cell_id"], cells, integer=True)
    if len(set(ids)) != cells or any(value < 0 for value in ids):
        raise PostprocessError("VTU 原始单元 ID 重复或无效")
    for value in centers:
        _finite(value)
    if any(_finite(value) <= 0 for value in volumes):
        raise PostprocessError("VTU 单元体积必须为有限正数")
    if vector:
        for component, suffix in enumerate(("x", "y", "z")):
            serialized = _numbers(arrays[field + "_" + suffix], cells)
            if any(not _same_value(value, values[index * 3 + component]) for index, value in enumerate(serialized)):
                raise PostprocessError("VTU 矢量分量与主字段不一致")
        magnitudes = _numbers(arrays[field + "_magnitude"], cells)
        for index, magnitude in enumerate(magnitudes):
            expected_magnitude = math.sqrt(sum(value * value for value in values[index * 3:index * 3 + 3]))
            if not _same_value(magnitude, expected_magnitude):
                raise PostprocessError("VTU 矢量模长与全部分量不一致")
    samples = []
    for index in range(cells):
        samples.append({
            "cell_id": ids[index], "center": centers[index * 3:index * 3 + 3], "volume": volumes[index],
            "value": values[index * components:index * components + components],
        })
    return dict(entry, time=physical_time, unit=unit, samples=samples)


def _read_monitors(path, declarations):
    monitors = {name: [] for name in declarations}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["step", "time"] + list(declarations):
            raise PostprocessError("标准 CSV 列与注册项不符")
        previous = None
        timed_steps = {}
        rows = 0
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise PostprocessError("标准 CSV 行列数不一致")
            step = int(row["step"])
            if step < 0:
                raise PostprocessError("标准 CSV 步数为负")
            time = _finite(row["time"]) if row["time"].strip() else None
            # The wide table may contain a timed and an iteration-only sample at one step.
            axis = (step, time is not None, time or 0)
            if previous is not None and axis <= previous:
                raise PostprocessError("标准 CSV 时间轴重复或倒序")
            previous = axis
            if time is not None:
                if step in timed_steps and timed_steps[step] != time:
                    raise PostprocessError("同一步对应不同物理时间")
                if timed_steps and time < next(reversed(timed_steps.values())):
                    raise PostprocessError("标准 CSV 物理时间倒序")
                timed_steps[step] = time
            sampled = False
            for name, declaration in declarations.items():
                if not row[name].strip():
                    continue
                sampled = True
                value = float(row[name])
                monitors[name].append({
                    "step": step, "time": time, "value": value, "unit": declaration.get("unit", ""),
                    "quality": "valid" if math.isfinite(value) else "invalid",
                })
            if declarations and not sampled:
                raise PostprocessError("标准 CSV 含完全未采样行")
            rows += 1
    if not rows or any(not records for records in monitors.values()):
        raise PostprocessError("标准 CSV 为空或缺少已注册监控曲线")
    return monitors


def load_observations(path, manifest):
    """从作业或归档的标准 CSV/VTU 独立回读观测值，失败抛出 PostprocessError。"""
    path = Path(path)
    try:
        case, condition = manifest["case"], manifest["condition"]
        inventory(path / "normalized")
        monitors = _read_monitors(path / "normalized" / "monitors.csv", case.get("monitors", {}))
        references = {}
        for reference in condition.get("references", {}).values():
            if "field" in reference:
                key = (reference["field"], reference["domain"])
                if key in references and isinstance(references[key]["expression"], dict) != isinstance(reference["expression"], dict):
                    raise PostprocessError("同一验证场存在矛盾分量定义")
                references[key] = reference
        entries = manifest.get("fields", [])
        directory = path / "normalized" / "fields"
        if not references:
            if entries or directory.exists():
                raise PostprocessError("无场参考解时不得保存 fields")
            if {item.name for item in (path / "normalized").iterdir()} != {"monitors.csv"}:
                raise PostprocessError("标准结果包含未声明文件")
            return {"monitors": monitors, "fields": []}
        if {item.name for item in (path / "normalized").iterdir()} != {"monitors.csv", "fields"}:
            raise PostprocessError("标准结果包含未声明文件")
        times = [_finite(entry["time"]) for entry in manifest["field_reader"]["times"]]
        if not times or any(right <= left for left, right in zip(times, times[1:])):
            raise PostprocessError("原生输出时刻清单为空、重复或倒序")
        expected = {(field, domain, time) for field, domain in references for time in times}
        actual = {(entry["field"], entry["domain"], _finite(entry["time"])) for entry in entries}
        if actual != expected or len(entries) != len(expected):
            raise PostprocessError("验证场没有覆盖所需域和全部实际输出时刻")
        files = [Path(entry["file"]) for entry in entries]
        # Old workspaces may still contain absolute paths; published archives must use relative paths.
        names = [file.name for file in files]
        if len(set(names)) != len(names) or set(names) != {file.name for file in directory.glob("*.vtu")}:
            raise PostprocessError("验证场文件清单重复、缺失或有额外文件")
        if {item.name for item in directory.iterdir()} - set(names) - {"fields.pvd"}:
            raise PostprocessError("验证场目录包含原生结果或未声明文件")
        datasets = []
        for entry in entries:
            file = directory / Path(entry["file"]).name
            declared = Path(entry["file"])
            if declared.is_absolute() and declared.resolve() != file.resolve():
                raise PostprocessError("标准场绝对路径指向其他作业")
            if not declared.is_absolute() and declared.as_posix() != "normalized/fields/" + file.name:
                raise PostprocessError("验证场文件必须引用归档内的规范相对路径")
            datasets.append(_read_vtu(file, entry, references[(entry["field"], entry["domain"])], case["fields"][entry["field"]]))
        pvd = directory / "fields.pvd"
        if pvd.exists():
            tree = _xml(pvd)
            if tree.get("type") != "Collection" or tree.find("Collection") is None:
                raise PostprocessError("PVD 不是有效时间集合")
            index = []
            for entry in tree.find("Collection"):
                if entry.tag != "DataSet" or Path(entry.get("file", "")).name != entry.get("file"):
                    raise PostprocessError("PVD 文件引用越界")
                index.append((entry.get("group"), _finite(entry.get("timestep")), entry.get("file")))
            wanted = [(entry["field"], float(entry["time"]), Path(entry["file"]).name) for entry in entries]
            if len(index) != len(wanted) or set(index) != set(wanted):
                raise PostprocessError("PVD 未完整引用实际输出场")
        return {"monitors": monitors, "fields": datasets}
    except PostprocessError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError, OverflowError, ConfigurationError) as exc:
        raise PostprocessError("标准结果无法独立读取: " + str(exc)) from exc


def _validate_contents(path, manifest):
    required = ("job_id", "identity", "case", "condition", "actual_solver", "execution", "input_sha256")
    if any(name not in manifest for name in required):
        raise PostprocessError("作业元数据不完整")
    if not isinstance(manifest["identity"], dict) or not manifest["identity"]:
        raise PostprocessError("缺少完整作业身份")
    if manifest["identity"].get("schema") == "simtest-identity/2":
        canonical = json.dumps(manifest["identity"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if manifest["job_id"] != expected:
            raise PostprocessError("稳定作业哈希与完整身份不一致")
    if not (path / "input").is_dir() or inventory(path / "input") != manifest["input_sha256"]:
        raise PostprocessError("只读输入快照缺失或被修改")
    if not manifest["input_sha256"]:
        raise PostprocessError("输入快照为空")
    if not (path / "logs").is_dir() or not inventory(path / "logs"):
        raise PostprocessError("缺少运行日志")
    return load_observations(path, manifest)


def validate_normalized(context):
    """校验输入、日志、元数据与标准结果；返回独立读取的监控及场数据。"""
    return _validate_contents(context.run_dir, context.manifest)


def manifest_digest(manifest):
    body = dict(manifest)
    body.pop("archive_integrity", None)
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def verify_archive(path):
    """同时验证不可变清单哈希和标准文件可读性；拒绝失败或不完整归档。"""
    path = Path(path)
    try:
        manifest = _json(path / "manifest.json")
        integrity = manifest["archive_integrity"]
        hashes = inventory(path)
        hashes.pop("manifest.json", None)
        if hashes != integrity["files"] or manifest_digest(manifest) != integrity["manifest_content_sha256"]:
            raise PostprocessError("归档完整性校验失败: " + str(path))
        if _json(path / "status.json")["status"] != "SUCCEEDED":
            raise PostprocessError("正式归档只保存完整成功作业")
        if {item.name for item in path.iterdir()} != {"manifest.json", "status.json", "input", "logs", "normalized"}:
            raise PostprocessError("归档包含原生结果或未声明目录")
        for entry in manifest.get("fields", []):
            file = Path(entry["file"])
            if file.is_absolute() or file.as_posix() != "normalized/fields/" + file.name:
                raise PostprocessError("归档字段路径不能依赖运行目录")
        _validate_contents(path, manifest)
    except PostprocessError:
        raise
    except (OSError, ValueError, TypeError, KeyError, ConfigurationError) as exc:
        raise PostprocessError("归档无法验证: " + str(exc)) from exc
    return True


def archive_path(context):
    """返回案例/工况/内核/实际版本/稳定身份对应的正式归档路径。"""
    parts = (context.case["id"], context.condition_id, context.info.name, context.info.version, context.run_dir.name)
    for part in parts:
        identifier(part)
    path = context.root / "artifacts" / parts[0] / "runs" / parts[1] / parts[2] / parts[3] / parts[4]
    for item in (path, *path.parents):
        if item.is_symlink():
            raise PostprocessError("归档路径不允许符号链接")
        if item == context.root:
            break
    return within(context.root / "artifacts", path)


def archive(context, status):
    """发布完整成功归档；不删除现场、不回写已发布的清单和状态。"""
    if status.get("status") != "SUCCEEDED":
        raise PostprocessError("只有完整成功作业可以发布正式归档")
    validate_normalized(context)
    final = archive_path(context)
    staging = final.parent / ("." + final.name + ".staging")
    if final.exists() or staging.exists():
        raise PostprocessError("拒绝覆盖已有归档或未完成暂存")
    staging.mkdir(parents=True)
    for name in ("input", "logs", "normalized"):
        shutil.copytree(context.run_dir / name, staging / name)
    atomic_json(staging / "status.json", status)
    manifest = json_safe(context.manifest)
    for entry in manifest.get("fields", []):
        entry["file"] = "normalized/fields/" + Path(entry["file"]).name
    manifest["archive_integrity"] = {"files": inventory(staging), "manifest_content_sha256": manifest_digest(manifest)}
    atomic_json(staging / "manifest.json", manifest)
    verify_archive(staging)
    staging.rename(final)
    verify_archive(final)
    return final


def cleanup_run(context, final):
    """仅在归档及标准结果均校验成功后，安全删除该作业整个工作区。"""
    final = Path(final)
    verify_archive(final)
    manifest = _json(final / "manifest.json")
    if manifest["job_id"] != context.run_dir.name or manifest["identity"] != json_safe(context.manifest["identity"]):
        raise PostprocessError("清理目标与归档作业身份不一致")
    root = Path(context.root).resolve()
    runs = root / "runs"
    run = Path(context.run_dir)
    if runs.is_symlink() or run.is_symlink() or run.parent.resolve() != runs.resolve() or run.name in ("", ".", ".."):
        raise PostprocessError("清理路径越界或包含符号链接")
    if final.resolve() != archive_path(context):
        raise PostprocessError("清理所依据的归档位置不符")
    target = within(runs, run)
    if target == runs or target.parent != runs.resolve():
        raise PostprocessError("拒绝清理工作区根目录")
    if not target.exists():
        return
    inventory(target)
    shutil.rmtree(target)


def archived_runs(root, case_id=None):
    """只列出已发布的正式成功归档，不包含暂存和失败现场。"""
    root = Path(root)
    if case_id:
        cases = [root / "artifacts" / identifier(case_id)]
    else:
        cases = sorted((root / "artifacts").glob("*"))
    result = []
    for case in cases:
        for file in sorted((case / "runs").glob("*/*/*/*/manifest.json")):
            if file.parent.name.startswith("."):
                continue
            manifest = _json(file)
            status = _json(file.parent / "status.json")
            if status["status"] != "SUCCEEDED":
                continue
            result.append({
                "case": case.name, "job_id": manifest["job_id"], "condition": manifest["identity"]["condition"],
                "solver": manifest["actual_solver"]["name"], "version": manifest["actual_solver"]["version"],
                "processes": manifest["execution"]["processes"], "status": status["status"],
                "created": manifest.get("created"), "archive": str(file.parent),
            })
    return sorted(result, key=lambda item: (item["created"] or "", item["job_id"]))
