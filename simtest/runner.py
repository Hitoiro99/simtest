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
from types import SimpleNamespace

from solvers.base import redact
from solvers.exceptions import (CancelledError, ConfigurationError, SolverCrashError,
                               SolverTimeoutError, UnsupportedCaseError, VersionMismatchError)
from solvers.models import RunContext
from solvers.registry import ADAPTERS, discover, select
from .analysis import field_comparisons, monitor_comparisons
from .archive import archive, archive_failure
from .cases import execution_config, load_case, load_condition
from .environment import activate
from .io import atomic_json, atomic_text, identifier, inventory, read_yaml


def setup(root,args):
    discover()
    if args.solver not in ADAPTERS: raise ConfigurationError("求解器没有注册")
    path = Path(args.path).resolve()
    if not path.is_dir(): raise ConfigurationError("安装根目录不存在")
    environment = {"kind":args.environment}
    if args.environment_script: environment["script"] = str(Path(args.environment_script).resolve())
    if args.environment_module: environment["modules"] = args.environment_module
    installation = {"solver":args.solver,"version":args.version,"path":str(path),"environment":environment}
    activated = activate(installation)
    public = min(ADAPTERS[args.solver].values(),key=lambda cls:cls.version_key(cls.version))()
    info = public.probe(SimpleNamespace(environment=activated))
    if info.version != args.version: raise VersionMismatchError("配置 %s 与真实 %s 不一致" % (args.version,info.version))
    if path not in Path(info.executables["icoFoam"]).parents:
        raise ConfigurationError("激活后的求解器不属于 --path 指定的安装")
    select(args.solver,info.version)
    file = Path(args.config).resolve() if args.config else root/"config.yaml"
    config = read_yaml(file) if file.exists() else {"installations":[]}
    if not isinstance(config.get("installations"),list): raise ConfigurationError("config.installations 必须为列表")
    existing = [item for item in config["installations"] if (item.get("solver"),str(item.get("version")))==(args.solver,args.version)]
    if len(existing)>1: raise ConfigurationError("部署配置有重复安装记录")
    if existing and not args.force: raise ConfigurationError("安装已登记；替换需使用 --force")
    config["installations"] = [item for item in config["installations"] if item not in existing]+[installation]
    import yaml
    atomic_text(file,yaml.safe_dump(config,allow_unicode=True,sort_keys=False))
    ignore = root/".gitignore"
    content = ignore.read_text() if ignore.exists() else ""
    if "config.yaml" not in content.splitlines(): atomic_text(ignore,content.rstrip()+"\nconfig.yaml\n")
    return {"config":str(file),"solver":info.__dict__}


def deployment(root,selector,config_file=None):
    discover()
    name,sep,requested = selector.partition("@")
    requested = requested if sep else "latest"
    if name not in ADAPTERS: raise UnsupportedCaseError("未注册求解器: " + name)
    config = read_yaml(Path(config_file) if config_file else root/"config.yaml")
    installations = [entry for entry in config.get("installations",[]) if entry.get("solver")==name and (requested=="latest" or str(entry.get("version"))==requested)]
    if not installations: raise ConfigurationError("没有匹配安装，请先 simtest setup")
    found = []
    public = min(ADAPTERS[name].values(),key=lambda cls:cls.version_key(cls.version))()
    for installation in installations:
        env = activate(installation)
        info = public.probe(SimpleNamespace(environment=env))
        if info.version != str(installation["version"]): raise VersionMismatchError("部署版本与探测版本不一致")
        actual_path = Path(info.executables["icoFoam"]).resolve()
        if Path(installation["path"]).resolve() not in actual_path.parents: raise VersionMismatchError("当前环境使用了另一安装的可执行文件")
        found.append((public.version_key(info.version),installation,env,info))
    found.sort(key=lambda item:item[0],reverse=True)
    if len(found)>1 and found[0][0]==found[1][0]: raise ConfigurationError("latest 对应多个同版本安装，请消除部署歧义")
    _,installation,env,info = found[0]
    return installation,env,info,select(name,info.version)


def git_revision(root):
    try:
        result = subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5)
        return result.stdout.decode().strip() if result.returncode==0 else None
    except (OSError,subprocess.TimeoutExpired): return None


def prepare_context(root,case_id,condition_id,selector,options):
    path = root/"cases"/identifier(case_id)
    case = load_case(path)
    condition,parameters = load_condition(path,case,condition_id)
    execution = execution_config(case.get("execution",{}))
    for name in ("processes","backend","openmp_threads"):
        value = getattr(options,name,None)
        if value is not None: execution[name]=value
    execution = execution_config(execution)
    installation,environment,info,adapter = deployment(root,selector,getattr(options,"config",None))
    nonce = uuid.uuid4().hex
    identity = {"case":case_id,"condition":condition_id,"solver":info.name,"version":info.version,"build":info.build,
                "execution":execution,"case_sha256":inventory(path),"installation_path":installation["path"],"nonce":nonce}
    encoded = json.dumps(identity,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    job_id = hashlib.sha256(encoded).hexdigest()[:24]
    run_dir = root/"runs"/job_id; run_dir.mkdir(parents=True,exist_ok=False)
    (run_dir/"logs").mkdir()
    context = RunContext(root,path,run_dir,case,condition,condition_id,parameters,execution,installation,environment,info,
                         options.timeout,options.heartbeat_timeout)
    code_hashes = {}
    for directory in (root/"simtest",root/"solvers"):
        code_hashes.update({str(directory.relative_to(root)/p):h for p,h in inventory(directory).items() if p.endswith((".py", ".js", ".css"))})
    from . import __version__
    cpu_info = Path("/proc/cpuinfo").read_text(errors="replace") if Path("/proc/cpuinfo").exists() else ""
    cpu_model = next((line.split(":",1)[1].strip() for line in cpu_info.splitlines() if line.startswith("model name")),platform.processor())
    from .environment import run_capture
    mpi_version = run_capture([info.executables["mpirun"],"--version"],environment).strip() if "mpirun" in info.executables else None
    context.manifest = {"schema":"simtest-run/1","platform_version":__version__,"job_id":job_id,"identity":identity,"id_method":"sha256 canonical identity incl. unique nonce; 24 hex + atomic mkdir",
                        "case_revision":case["version"],"case":case,"condition":condition,"parameters":parameters,
                        "actual_solver":info.__dict__,"adapter":{"name":adapter.name,"version":adapter.version,"version_rule":"Foundation integer release; same branch only"},
                        "system":{"os":platform.platform(),"host":socket.gethostname(),"cpu":cpu_model,"logical_cpus":os.cpu_count(),"gpu":None,"container_digest":None,"mpi":mpi_version,
                                  "filesystem":"WSL mounted workspace" if str(root).startswith("/mnt/") else "Linux native"},
                        "execution":execution,"git_commit":git_revision(root),"git_unavailable_reason":None if git_revision(root) else "workspace has no readable Git commit; exact source SHA-256 recorded","code_sha256":code_hashes,
                        "environment":{key:redact(environment[key]) for key in ("WM_PROJECT_VERSION","WM_PROJECT_DIR","WM_OPTIONS","OMP_NUM_THREADS") if key in environment},
                        "created":datetime.datetime.now(datetime.timezone.utc).isoformat()}
    return context,adapter


def run_job(context,adapter,prepare_only=False,keep_raw=False):
    status = {"status":"CREATED","history":[],"diagnostics":context.diagnostics,"raw_results":"retained_until_validations"}
    def transition(value):
        status["status"]=value
        status["history"].append({"status":value,"time":datetime.datetime.now(datetime.timezone.utc).isoformat()})
        atomic_json(context.run_dir/"status.json",status)
        atomic_json(context.run_dir/"manifest.json",context.manifest)
    transition("CREATED")
    try:
        transition("VALIDATING"); adapter.validate(context)
        transition("PREPROCESSING"); result = adapter.preprocess(context)
        context.manifest["preprocess"] = result.diagnostics
        transition("QUEUED")
        if prepare_only:
            status["prepared_only"]=True; atomic_json(context.run_dir/"status.json",status)
            return {"job_id":context.run_dir.name,"status":"QUEUED","run":str(context.run_dir)}
        transition("RUNNING"); result = adapter.execute(context)
        context.manifest["execution_result"] = result.diagnostics
        transition("POSTPROCESSING"); result = adapter.postprocess(context)
        context.manifest["comparisons"] = {"monitors":monitor_comparisons(context),"fields":field_comparisons(context,result.diagnostics.get("fields",[]))}
        transition("SUCCEEDED")
        status["raw_results"] = "retained_by_request" if keep_raw else "cleanup_after_archive_verification"
        atomic_json(context.run_dir/"status.json",status)
        atomic_json(context.run_dir/"manifest.json",context.manifest)
        final = archive(context,status,cleanup=not keep_raw)
        return {"job_id":context.run_dir.name,"status":"SUCCEEDED","archive":str(final)}
    except Exception as exc:
        state = "UNSUPPORTED" if isinstance(exc,UnsupportedCaseError) else "TIMEOUT" if isinstance(exc,SolverTimeoutError) else "CRASHED" if isinstance(exc,SolverCrashError) else "CANCELLED" if isinstance(exc,CancelledError) else "INFRA_ERROR"
        context.diagnostics.append({"kind":type(exc).__name__,"stage":getattr(exc,"stage",None) or status["status"],"message":redact(str(exc)),"details":getattr(exc,"diagnostics",{})})
        status["raw_results"]="retained_due_to_failure"
        transition(state)
        try: final = archive_failure(context,status)
        except Exception as archive_error:
            context.diagnostics.append({"kind":"archive_failure","message":str(archive_error)})
            atomic_json(context.run_dir/"status.json",status); final = None
        return {"job_id":context.run_dir.name,"status":state,"run":str(context.run_dir),"archive":str(final) if final else None,"error":str(exc)}
