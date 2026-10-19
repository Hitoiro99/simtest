"""独立作业创建、追溯记录和运行流程控制。"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import socket
import subprocess
import uuid
from pathlib import Path

from case_management.cases import execution_config, load_case, load_condition
from common.io import atomic_json, identifier, inventory, sha256
from postprocessing.analysis import field_comparisons, monitor_comparisons
from run_control.install import select_install
from solvers.base import redact
from solvers.exceptions import CancelledError, SolverCrashError, SolverTimeoutError, UnsupportedCaseError
from solvers.models import RunContext
from storage.archive import archive, archive_failure


def _git_revision(root):
    """读取工作区 Git 提交号；Git 不可用、超时或工作区没有提交时返回 None。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.decode().strip()
        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _build_manifest(context, identity, adapter):
    """收集版本、源码、硬件和环境追溯信息，返回本次作业的清单字典。"""
    root = context.root
    case = context.case
    condition = context.condition
    parameters = context.parameters
    execution = context.execution
    environment = context.environment
    info = context.info
    job_id = context.run_dir.name

    source_root = Path(__file__).resolve().parents[1]
    code_hashes = {"simtest.py": sha256(source_root / "simtest.py")}
    for name in ("case_management", "run_control", "postprocessing", "reporting", "storage", "common", "solvers"):
        directory = source_root / name
        code_hashes.update(
            {
                str(directory.relative_to(source_root) / p): h
                for p, h in inventory(directory).items()
                if p.endswith((".py", ".js", ".css"))
            }
        )
    from common.version import __version__

    if Path("/proc/cpuinfo").exists():
        cpu_info = Path("/proc/cpuinfo").read_text(errors="replace")
    else:
        cpu_info = ""
    cpu_model = next(
        (line.split(":", 1)[1].strip() for line in cpu_info.splitlines() if line.startswith("model name")),
        platform.processor(),
    )
    from run_control.environment import run_capture

    if "mpirun" in info.executables:
        mpi_version = run_capture([info.executables["mpirun"], "--version"], environment).strip()
    else:
        mpi_version = None

    manifest = {
        "schema": "simtest-run/1",
        "platform_version": __version__,
        "job_id": job_id,
        "identity": identity,
        "id_method": "sha256 canonical identity incl. unique nonce; 24 hex + atomic mkdir",
        "case_revision": case["version"],
        "case": case,
        "condition": condition,
        "parameters": parameters,
        "actual_solver": info.__dict__,
        "adapter": {
            "name": adapter.name,
            "version": adapter.version,
            "version_rule": "Foundation integer release; same branch only",
        },
        "system": {
            "os": platform.platform(),
            "host": socket.gethostname(),
            "cpu": cpu_model,
            "logical_cpus": os.cpu_count(),
            "gpu": None,
            "container_digest": None,
            "mpi": mpi_version,
            "filesystem": "WSL mounted workspace" if str(root).startswith("/mnt/") else "Linux native",
        },
        "execution": execution,
    }
    manifest["git_commit"] = _git_revision(root)
    if _git_revision(root):
        manifest["git_unavailable_reason"] = None
    else:
        manifest["git_unavailable_reason"] = "workspace has no readable Git commit; exact source SHA-256 recorded"
    manifest["code_sha256"] = code_hashes
    manifest["environment"] = {
        key: redact(environment[key])
        for key in ("WM_PROJECT_VERSION", "WM_PROJECT_DIR", "WM_OPTIONS", "OMP_NUM_THREADS")
        if key in environment
    }
    manifest["created"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return manifest


def prepare_job(root, case_id, condition_id, selector, options):
    """解析案例及 CLI 选项并创建独立作业，返回上下文和 Adapter；不物化求解输入，配置无效时抛出异常。"""
    path = root / "cases" / identifier(case_id)
    case = load_case(path)
    condition, parameters = load_condition(path, case, condition_id)

    execution = execution_config(case.get("execution", {}))
    for name in ("processes", "backend", "openmp_threads"):
        value = getattr(options, name, None)
        if value is not None:
            execution[name] = value
    execution = execution_config(execution)
    installation, environment, info, adapter = select_install(root, selector, getattr(options, "config", None))

    nonce = uuid.uuid4().hex
    identity = {
        "case": case_id,
        "condition": condition_id,
        "solver": info.name,
        "version": info.version,
        "build": info.build,
        "execution": execution,
        "case_sha256": inventory(path),
        "installation_path": installation["path"],
        "nonce": nonce,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    job_id = hashlib.sha256(encoded).hexdigest()[:24]

    run_dir = root / "runs" / job_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "logs").mkdir()
    context = RunContext(
        root,
        path,
        run_dir,
        case,
        condition,
        condition_id,
        parameters,
        execution,
        installation,
        environment,
        info,
        options.timeout,
        options.heartbeat_timeout,
    )

    context.manifest = _build_manifest(context, identity, adapter)
    return context, adapter


def run_job(context, adapter, prepare_only=False, keep_raw=False):
    """按阶段运行作业并返回状态及路径；准备模式停在 QUEUED，阶段异常记录诊断并保留失败现场。"""
    status = {
        "status": "CREATED",
        "history": [],
        "diagnostics": context.diagnostics,
        "raw_results": "retained_until_validations",
    }

    def _record_state(value):
        """追加本作业状态历史，并保存状态和当前清单。"""
        status["status"] = value
        status["history"].append({"status": value, "time": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        atomic_json(context.run_dir / "status.json", status)
        atomic_json(context.run_dir / "manifest.json", context.manifest)

    _record_state("CREATED")
    try:
        _record_state("VALIDATING")
        adapter.validate(context)

        _record_state("PREPROCESSING")
        result = adapter.preprocess(context)
        context.manifest["preprocess"] = result.diagnostics
        _record_state("QUEUED")
        if prepare_only:
            status["prepared_only"] = True
            atomic_json(context.run_dir / "status.json", status)
            return {"job_id": context.run_dir.name, "status": "QUEUED", "run": str(context.run_dir)}

        _record_state("RUNNING")
        result = adapter.execute(context)
        context.manifest["execution_result"] = result.diagnostics

        _record_state("POSTPROCESSING")
        result = adapter.postprocess(context)
        context.manifest["comparisons"] = {
            "monitors": monitor_comparisons(context),
            "fields": field_comparisons(context, result.diagnostics.get("fields", [])),
        }

        _record_state("SUCCEEDED")
        status["raw_results"] = "retained_by_request" if keep_raw else "cleanup_after_archive_verification"
        atomic_json(context.run_dir / "status.json", status)
        atomic_json(context.run_dir / "manifest.json", context.manifest)
        final = archive(context, status, cleanup=not keep_raw)
        return {"job_id": context.run_dir.name, "status": "SUCCEEDED", "archive": str(final)}
    except Exception as exc:
        if isinstance(exc, UnsupportedCaseError):
            state = "UNSUPPORTED"
        elif isinstance(exc, SolverTimeoutError):
            state = "TIMEOUT"
        elif isinstance(exc, SolverCrashError):
            state = "CRASHED"
        elif isinstance(exc, CancelledError):
            state = "CANCELLED"
        else:
            state = "INFRA_ERROR"

        context.diagnostics.append(
            {
                "kind": type(exc).__name__,
                "stage": getattr(exc, "stage", None) or status["status"],
                "message": redact(str(exc)),
                "details": getattr(exc, "diagnostics", {}),
            }
        )
        status["raw_results"] = "retained_due_to_failure"
        _record_state(state)

        try:
            final = archive_failure(context, status)
        except Exception as archive_error:
            context.diagnostics.append({"kind": "archive_failure", "message": str(archive_error)})
            atomic_json(context.run_dir / "status.json", status)
            final = None

        if final:
            archive_path = str(final)
        else:
            archive_path = None
        return {
            "job_id": context.run_dir.name,
            "status": state,
            "run": str(context.run_dir),
            "archive": archive_path,
            "error": str(exc),
        }
