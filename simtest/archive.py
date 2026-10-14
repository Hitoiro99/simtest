import csv
import hashlib
import json
import shutil
from pathlib import Path

from solvers.exceptions import PostprocessError
from .io import atomic_json, inventory, within


def validate_normalized(context):
    monitor_file = context.normalized/"monitors.csv"
    with monitor_file.open(newline="",encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["step","time"]+list(context.case.get("monitors",{})):
            raise PostprocessError("标准 CSV 列与注册项不符")
        count = 0
        for row in reader:
            int(row["step"])
            if row["time"]: float(row["time"])
            for name in context.case.get("monitors",{}):
                if row[name]: float(row[name])
            count += 1
        if not count: raise PostprocessError("标准 CSV 为空")
    fields = context.manifest.get("fields",[])
    actual = {p.name for p in (context.normalized/"fields").glob("*.vtu")}
    if actual != {Path(d["file"]).name for d in fields}: raise PostprocessError("场文件清单不完整或包含多余字段文件")
    if fields and not (context.normalized/"fields"/"fields.pvd").is_file(): raise PostprocessError("缺少场时间索引")
    if inventory(context.input) != context.manifest["input_sha256"]: raise PostprocessError("只读输入快照被修改")


def manifest_digest(manifest):
    body = dict(manifest); body.pop("archive_integrity",None)
    return hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def verify_archive(path):
    path = Path(path)
    manifest = json.loads((path/"manifest.json").read_text())
    integrity = manifest["archive_integrity"]
    hashes = inventory(path); hashes.pop("manifest.json",None)
    if hashes != integrity["files"] or manifest_digest(manifest)!=integrity["manifest_content_sha256"]:
        raise PostprocessError("归档完整性校验失败: " + str(path))
    return True


def archive(context,status,cleanup=True):
    validate_normalized(context)
    final = context.root/"artifacts"/context.case["id"]/"runs"/context.condition_id/context.info.name/context.info.version/context.run_dir.name
    staging = final.parent/("."+final.name+".staging")
    if final.exists() or staging.exists(): raise PostprocessError("拒绝覆盖历史归档")
    staging.mkdir(parents=True)
    for name in ("input","logs","normalized"): shutil.copytree(context.run_dir/name,staging/name)
    atomic_json(staging/"status.json",status)
    # Round-trip JSON makes nonfinite diagnostic values explicit strings.
    manifest = json.loads((context.run_dir/"manifest.json").read_text())
    manifest["archive_integrity"] = {"files":inventory(staging),"manifest_content_sha256":manifest_digest(manifest)}
    atomic_json(staging/"manifest.json",manifest)
    verify_archive(staging)
    staging.rename(final)
    verify_archive(final)
    if cleanup:
        work = within(context.root/"runs",context.work)
        if work.parent != context.run_dir.resolve() or work.name != "work": raise PostprocessError("清理路径越界")
        shutil.rmtree(work)
    status["archive"] = str(final)
    status["raw_results"] = "cleaned_after_two_validations" if cleanup else "retained_by_request"
    atomic_json(context.run_dir/"status.json",status)
    return final


def archive_failure(context,status):
    final = context.root/"artifacts"/context.case["id"]/"runs"/context.condition_id/context.info.name/context.info.version/context.run_dir.name
    if final.exists(): return final
    staging = final.parent/("."+final.name+".failed-staging")
    staging.mkdir(parents=True,exist_ok=False)
    for name in ("input","logs"):
        if (context.run_dir/name).exists(): shutil.copytree(context.run_dir/name,staging/name)
    atomic_json(staging/"status.json",status)
    manifest = json.loads((context.run_dir/"manifest.json").read_text())
    manifest["archive_integrity"] = {"files":inventory(staging),"manifest_content_sha256":manifest_digest(manifest)}
    atomic_json(staging/"manifest.json",manifest)
    verify_archive(staging); staging.rename(final)
    return final
