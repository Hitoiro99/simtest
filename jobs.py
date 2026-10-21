"""稳定作业身份、并发单写、运行流程和归档复用。"""

from __future__ import annotations

from contextlib import contextmanager
import datetime
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import socket
import subprocess
import sys

from analysis import field_comparisons, monitor_comparisons
from archive import archive, archive_path, cleanup_run, verify_archive
from case_management.cases import execution_config, execution_configs, load_case, load_condition
from common.io import atomic_json, identifier, inventory, sha256, within
from solvers.base import redact, run_capture
from solvers.exceptions import (
    CancelledError,
    ConfigurationError,
    SolverCrashError,
    SolverTimeoutError,
    UnsupportedCaseError,
)
from solvers.models import RunContext
from solvers.registry import select_install


TERMINAL_STATES = {"SUCCEEDED", "TIMEOUT", "CRASHED", "INFRA_ERROR", "UNSUPPORTED", "CANCELLED"}


def _canonical(value):
    """生成 UTF-8 规范 JSON，固定键序和分隔符，拒绝非有限数值。"""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _git_revision(root):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.decode().strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def code_inventory():
    """返回受维护执行代码的相对路径和内容哈希；不包含文档、缓存或运行生成物。"""
    source_root = Path(__file__).resolve().parent
    hashes = {name: sha256(source_root / name) for name in ("simtest.py", "jobs.py", "analysis.py", "archive.py", "report.py")}
    for name in ("case_management", "report_assets", "common", "solvers"):
        for relative, digest in inventory(source_root / name).items():
            if relative.endswith((".py", ".js", ".css")):
                hashes[(Path(name) / relative).as_posix()] = digest
    return hashes


def _read_system(path):
    file = Path(path)
    if file.is_file():
        return file.read_text(encoding="utf-8", errors="replace").strip()
    return None


def hardware_info(execution, info, environment):
    """采集稳定载体、硬件及资源限制；不记录时钟、负载、空闲内存或其他运行后统计。"""
    machine = _read_system("/etc/machine-id") or _read_system("/var/lib/dbus/machine-id")
    cpu_text = _read_system("/proc/cpuinfo")
    mem_text = _read_system("/proc/meminfo")
    if not machine or not cpu_text or not mem_text:
        raise ConfigurationError("无法取得稳定主机、CPU 或内存身份，不能安全判重")
    cpu_models = sorted({line.split(":", 1)[1].strip() for line in cpu_text.splitlines() if line.startswith("model name")})
    total = re.search(r"(?m)^MemTotal:\s*(\d+)\s+kB", mem_text)
    if not cpu_models or not total:
        raise ConfigurationError("CPU 型号或物理内存身份不完整")
    memory_root = Path("/sys/devices/system/memory")
    block_size = _read_system(memory_root / "block_size_bytes")
    blocks = [block for block in memory_root.glob("memory[0-9]*") if (_read_system(block / "state") or "").startswith("online")]
    if not block_size or not blocks:
        raise ConfigurationError("无法取得稳定内存块容量，不能用运行期 MemTotal 安全判重")
    memory_bytes = int(block_size, 16) * len(blocks)
    cgroup = {}
    membership = _read_system("/proc/self/cgroup") or ""
    mounts = {"unified": Path("/sys/fs/cgroup")}
    for line in membership.splitlines():
        hierarchy, controllers, relative = line.split(":", 2)
        if controllers:
            for controller in controllers.split(","):
                mounts[controller] = Path("/sys/fs/cgroup") / controller / relative.lstrip("/")
        else:
            mounts["unified"] = Path("/sys/fs/cgroup") / relative.lstrip("/")
    limits = {
        "unified": ("cpu.max", "memory.max", "cpuset.cpus.effective", "cpuset.mems.effective"),
        "cpu": ("cpu.cfs_quota_us", "cpu.cfs_period_us"),
        "memory": ("memory.limit_in_bytes",),
        "cpuset": ("cpuset.cpus", "cpuset.mems"),
    }
    for controller, names in limits.items():
        directory = mounts.get(controller)
        if directory is None:
            continue
        base = Path("/sys/fs/cgroup").resolve()
        directory = directory.resolve()
        if directory != base and base not in directory.parents:
            raise ConfigurationError("资源配额路径越界")
        while True:
            values = {}
            for name in names:
                value = _read_system(directory / name)
                if value is not None:
                    values[name] = value
            if values:
                cgroup[str(directory.relative_to(base))] = values
            if directory == base:
                break
            directory = directory.parent
    process_limits = {}
    for name in ("RLIMIT_AS", "RLIMIT_CPU", "RLIMIT_NPROC", "RLIMIT_NOFILE", "RLIMIT_STACK"):
        if hasattr(resource, name):
            process_limits[name] = list(resource.getrlimit(getattr(resource, name)))
    gpus = []
    nvidia = shutil.which("nvidia-smi", path=environment.get("PATH"))
    if nvidia:
        output = run_capture(
            [nvidia, "--query-gpu=uuid,name,driver_version,memory.total", "--format=csv,noheader,nounits"], environment
        )
        gpus = sorted(line.strip() for line in output.splitlines() if line.strip())
    container = Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()
    digest = environment.get("SIMTEST_CONTAINER_DIGEST")
    if container and not digest:
        raise ConfigurationError("容器运行必须提供 SIMTEST_CONTAINER_DIGEST，不能将未知镜像视为相同载体")
    mpi = None
    if "mpirun" in info.executables:
        mpi = run_capture([info.executables["mpirun"], "--version"], environment).strip()
    affinity = None
    if hasattr(os, "sched_getaffinity"):
        affinity = sorted(os.sched_getaffinity(0))
    return {
        "machine": hashlib.sha256(machine.encode("utf-8")).hexdigest(),
        "host": socket.gethostname(),
        "os": platform.platform(),
        "architecture": platform.machine(),
        "cpu": cpu_models,
        "logical_cpus": os.cpu_count(),
        "memory_bytes": memory_bytes,
        "affinity": affinity,
        "resource_limits": cgroup,
        "process_limits": process_limits,
        "gpus": gpus,
        "container_digest": digest,
        "mpi": mpi,
    }


def prepare_job(root, case_id, condition_id, selector, options, execution=None):
    """探测并规范化完整运行身份，返回上下文和 Adapter；不创建工作区或写入重复记录。"""
    root = Path(root).resolve()
    path = root / "cases" / identifier(case_id)
    case = load_case(path)
    condition, parameters = load_condition(path, case, condition_id)
    if execution is None:
        execution = execution_configs(case.get("execution", {}))[0]
    else:
        execution = execution_config(execution)
    for name in ("processes", "backend", "openmp_threads"):
        value = getattr(options, name, None)
        if value is not None:
            execution[name] = value
    execution = execution_config(execution)
    installation, environment, info, adapter = select_install(root, selector, getattr(options, "config", None))
    code_hashes = code_inventory()
    system = hardware_info(execution, info, environment)
    executables = {}
    for name, value in info.executables.items():
        executable = Path(value).resolve()
        executables[name] = {"path": str(executable), "sha256": sha256(executable)}
    environment_hashes = {}
    public_environment = {}
    environment_keys = set(adapter.environment_keys)
    prefixes = ("OMP_", "OMPI_", "MPI_", "I_MPI_", "MPICH_", "CUDA_", "NVIDIA_", "MKL_", "OPENBLAS_")
    for key in environment:
        if key.startswith(prefixes) or key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "SIMTEST_CONTAINER_DIGEST"):
            environment_keys.add(key)
    for key in sorted(environment_keys):
        if key not in environment:
            continue
        value = environment[key]
        environment_hashes[key] = hashlib.sha256(value.encode("utf-8")).hexdigest()
        if re.search("password|token|secret|license|api_key", key, re.I):
            public_environment[key] = "[REDACTED]"
        else:
            public_environment[key] = redact(value)
    deployment = dict(installation)
    spec = dict(deployment.get("environment", {}))
    if spec.get("kind") == "script":
        spec["script"] = str(Path(spec["script"]).resolve())
        spec["script_sha256"] = sha256(Path(spec["script"]))
    deployment["environment"] = spec
    deployment["path"] = str(Path(deployment["path"]).resolve())
    timeout = float(options.timeout)
    heartbeat_timeout = float(options.heartbeat_timeout)
    identity = {
        "schema": "simtest-identity/2",
        "case": case_id,
        "condition": condition_id,
        "case_revision": case["version"],
        "parameters": parameters,
        "solver": info.name,
        "version": info.version,
        "build": info.build,
        "branch": info.branch,
        "adapter_version": adapter.version,
        "execution": execution,
        "timeout": timeout,
        "heartbeat_timeout": heartbeat_timeout,
        "case_sha256": inventory(path),
        "code_sha256": code_hashes,
        "deployment": deployment,
        "executables": executables,
        "environment_sha256": environment_hashes,
        "system": system,
        "python": {
            "version": platform.python_version(),
            "executable_sha256": sha256(Path(sys.executable).resolve()),
            "dependencies": {name: metadata.version(name) for name in ("PyYAML", "Jinja2")},
        },
    }
    job_id = hashlib.sha256(_canonical(identity)).hexdigest()
    context = RunContext(
        root, path, root / "runs" / job_id, case, condition, condition_id, parameters,
        execution, installation, environment, info, timeout, heartbeat_timeout,
    )
    from common.version import __version__

    revision = _git_revision(root)
    context.manifest = {
        "schema": "simtest-run/2",
        "platform_version": __version__,
        "job_id": job_id,
        "identity": identity,
        "id_method": "SHA-256 full canonical simtest-identity/2; excludes timestamps, elapsed metrics and paths generated by jobs",
        "case_revision": case["version"],
        "case": case,
        "condition": condition,
        "parameters": parameters,
        "actual_solver": info.__dict__,
        "adapter": {"name": adapter.name, "version": adapter.version, "version_rule": adapter.version_rule},
        "system": system,
        "execution": execution,
        "code_sha256": code_hashes,
        "environment": public_environment,
        "git_commit": revision,
        "git_unavailable_reason": None if revision else "No readable Git commit; exact code hashes recorded",
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return context, adapter


@contextmanager
def _job_lock(context):
    """原子预约工作区并持有单作业进程锁；不同身份可以并行，等待者取得锁后重新检查归档。"""
    if os.name != "posix":
        raise ConfigurationError("作业并发控制必须在 Linux/WSL 内运行")
    import fcntl

    runs = context.root / "runs"
    if runs.is_symlink() or context.run_dir.is_symlink():
        raise ConfigurationError("工作区不允许符号链接")
    runs.mkdir(parents=True, exist_ok=True)
    if context.run_dir.parent.resolve() != runs.resolve():
        raise ConfigurationError("作业路径越界")
    stream = None
    with (runs / ".lock").open("a+b") as gate:
        fcntl.flock(gate, fcntl.LOCK_EX)
        if context.run_dir.exists() or not archive_path(context).exists():
            context.run_dir.mkdir(exist_ok=True)
            try:
                stream = (context.run_dir / ".lock").open("a+b")
            except FileNotFoundError:
                if not archive_path(context).exists():
                    raise
        fcntl.flock(gate, fcntl.LOCK_UN)
    if stream is not None:
        fcntl.flock(stream, fcntl.LOCK_EX)
    try:
        yield
    finally:
        if stream is not None:
            fcntl.flock(stream, fcntl.LOCK_UN)
            stream.close()


def _same_identity(context, manifest):
    if manifest.get("job_id") != context.run_dir.name or _canonical(manifest.get("identity")) != _canonical(context.manifest["identity"]):
        raise ConfigurationError("作业哈希对应的完整身份不一致，拒绝覆盖或复用")


def _complete(context, final, reused):
    result = {"job_id": context.run_dir.name, "status": "SUCCEEDED", "archive": str(final), "reused": reused}
    try:
        cleanup_run(context, final)
    except Exception as exc:
        result["cleanup_pending"] = True
        result["cleanup_error"] = redact(str(exc))
        status_file = context.run_dir / "status.json"
        if context.run_dir.is_dir():
            status = json.loads((final / "status.json").read_text(encoding="utf-8"))
            status["cleanup_pending"] = True
            status["cleanup_error"] = result["cleanup_error"]
            status["raw_results"] = "retained_due_to_cleanup_error"
            try:
                atomic_json(status_file, status)
            except OSError as write_error:
                result["cleanup_error"] += "; 状态写入失败: " + redact(str(write_error))
    return result


def run_job(context, adapter, prepare_only=False):
    """单写运行或复用同身份作业；成功归档后移除工作区，失败仅保留现场且不自动重试。"""
    with _job_lock(context):
        final = archive_path(context)
        if final.exists():
            verify_archive(final)
            _same_identity(context, json.loads((final / "manifest.json").read_text(encoding="utf-8")))
            return _complete(context, final, True)
        existing = None
        status_file = context.run_dir / "status.json"
        if status_file.exists():
            saved = json.loads((context.run_dir / "manifest.json").read_text(encoding="utf-8"))
            _same_identity(context, saved)
            context.manifest = saved
            existing = json.loads(status_file.read_text(encoding="utf-8"))
            context.diagnostics = existing["diagnostics"]
            if existing["status"] in TERMINAL_STATES and existing["status"] != "SUCCEEDED":
                return {
                    "job_id": context.run_dir.name, "status": existing["status"], "run": str(context.run_dir),
                    "reused": True, "error": "同身份作业已终止；保留原诊断，不自动重试", "archive": None,
                }
        (context.run_dir / "logs").mkdir(exist_ok=True)
        status = existing or {"status": "CREATED", "history": [], "diagnostics": context.diagnostics, "raw_results": "retained_until_validations"}

        def record(value):
            status["status"] = value
            status["history"].append({"status": value, "time": datetime.datetime.now(datetime.timezone.utc).isoformat()})
            atomic_json(context.run_dir / "manifest.json", context.manifest)
            atomic_json(status_file, status)

        try:
            if existing:
                if existing["status"] != "QUEUED" or not existing.get("prepared_only"):
                    raise ConfigurationError("原执行进程已退出且作业未终结，保留中断现场，不自动重启")
                if inventory(context.input) != context.manifest["input_sha256"] or inventory(context.work) != context.manifest["prepared_work_sha256"]:
                    raise ConfigurationError("准备后的输入或工作区被修改，拒绝接续")
                if inventory(context.case_path) != context.manifest["identity"]["case_sha256"]:
                    raise ConfigurationError("源案例已变化，拒绝用旧身份接续")
                adapter.validate(context)
                if prepare_only:
                    return {"job_id": context.run_dir.name, "status": "QUEUED", "run": str(context.run_dir), "reused": True}
                status["prepared_only"] = False
            else:
                record("CREATED")
                record("VALIDATING")
                adapter.validate(context)
                if inventory(context.case_path) != context.manifest["identity"]["case_sha256"]:
                    raise ConfigurationError("源案例在身份采集后发生变化")
                record("PREPROCESSING")
                result = adapter.preprocess(context)
                context.manifest["preprocess"] = result.diagnostics
                if inventory(context.case_path) != context.manifest["identity"]["case_sha256"]:
                    raise ConfigurationError("准备过程中源案例发生变化")
                context.manifest["prepared_work_sha256"] = inventory(context.work)
                record("QUEUED")
                if prepare_only:
                    status["prepared_only"] = True
                    atomic_json(context.run_dir / "manifest.json", context.manifest)
                    atomic_json(status_file, status)
                    return {"job_id": context.run_dir.name, "status": "QUEUED", "run": str(context.run_dir), "reused": False}
            record("RUNNING")
            result = adapter.execute(context)
            context.manifest["execution_result"] = result.diagnostics
            record("POSTPROCESSING")
            result = adapter.postprocess(context)
            context.manifest["comparisons"] = {
                "monitors": monitor_comparisons(context),
                "fields": field_comparisons(context, result.diagnostics.get("fields", [])),
            }
            atomic_json(context.run_dir / "manifest.json", context.manifest)
            final_status = dict(status)
            final_status["status"] = "SUCCEEDED"
            final_status["history"] = status["history"] + [{"status": "SUCCEEDED", "time": datetime.datetime.now(datetime.timezone.utc).isoformat()}]
            final_status["raw_results"] = "not_archived"
            final = archive(context, final_status)
            return _complete(context, final, False)
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
            context.diagnostics.append({
                "kind": type(exc).__name__, "stage": getattr(exc, "stage", None) or status["status"],
                "message": redact(str(exc)), "details": getattr(exc, "diagnostics", {}),
            })
            status["raw_results"] = "retained_due_to_failure"
            record(state)
            return {"job_id": context.run_dir.name, "status": state, "run": str(context.run_dir), "archive": None, "error": redact(str(exc)), "reused": False}
