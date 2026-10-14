import os
import shutil
import subprocess
from pathlib import Path

from solvers.exceptions import ConfigurationError, PreprocessError


def activate(installation):
    spec = installation.get("environment", {"kind":"existing"})
    kind = spec.get("kind")
    base = dict(os.environ)
    if kind == "existing":
        if "modules" in spec or "script" in spec: raise ConfigurationError("existing 不允许模块或脚本参数")
        return base
    if kind == "script":
        if "modules" in spec: raise ConfigurationError("script 不允许 modules")
        script = spec.get("script")
        if not isinstance(script, str) or not Path(script).is_file(): raise ConfigurationError("环境脚本不存在")
        argv = ["bash", "-c", 'source "$1" >/dev/null || exit $?; env -0', "simtest", script]
    elif kind == "module":
        if "script" in spec: raise ConfigurationError("module 不允许 script")
        modules = spec.get("modules")
        if not isinstance(modules, list) or not modules or not all(isinstance(m, str) and m and not m.startswith("-") for m in modules):
            raise ConfigurationError("非法模块参数")
        argv = ["bash", "-lc", 'module load "$@" >/dev/null || exit $?; env -0', "simtest"]+modules
    else: raise ConfigurationError("未知 environment.kind")
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=base, timeout=30)
    if result.returncode: raise PreprocessError("环境加载失败: " + result.stderr.decode("utf-8", "replace")[-2000:])
    environment = {}
    for pair in result.stdout.split(b"\0"):
        if b"=" in pair:
            key, value = pair.split(b"=", 1)
            environment[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    environment["OMP_NUM_THREADS"] = "1"
    return environment


def executable(name, environment):
    path = shutil.which(name, path=environment.get("PATH"))
    if not path: raise ConfigurationError("缺少可执行文件: " + name)
    return str(Path(path).resolve())


def run_capture(argv, environment, cwd=None, timeout=30):
    result = subprocess.run(argv, cwd=str(cwd) if cwd else None, env=environment,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    output = result.stdout.decode("utf-8", "replace")
    if result.returncode: raise PreprocessError("命令失败 %s: %s" % (argv[0], output[-3000:]))
    return output
