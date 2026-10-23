from __future__ import annotations

import importlib
import os
import pkgutil
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

from platform_support.io import atomic_text, read_yaml

from .exceptions import ConfigurationError, PreprocessError, UnsupportedCaseError, VersionMismatchError

ADAPTERS = {}


def _branch(adapter):
    return getattr(adapter, "branch", "") or ""


def _classes(name, branch=None):
    versions = ADAPTERS.get(name, {})
    if branch is None:
        return list(versions.values())
    return [cls for cls in versions.values() if _branch(cls) == branch]


def _branch_for_version(name, version):
    matches = [cls for cls in ADAPTERS.get(name, {}).values() if cls.version == str(version)]
    branches = {_branch(cls) for cls in matches}
    if len(branches) == 1:
        return branches.pop()
    if not branches:
        return None
    raise ConfigurationError("版本 %s 同时属于多个分支，必须显式指定 branch" % version)


def register_adapter(cls):
    if not isinstance(getattr(cls, "name", None), str) or not isinstance(getattr(cls, "version", None), str):
        raise ConfigurationError("Adapter 缺少 name/version")
    if not isinstance(getattr(cls, "branch", ""), str):
        raise ConfigurationError("Adapter.branch 必须为字符串")
    if getattr(cls, "__abstractmethods__", None):
        raise ConfigurationError("Adapter 未实现所有必需接口")
    for parent in cls.__mro__[1:]:
        if hasattr(parent, "name") and parent.name != cls.name:
            raise ConfigurationError("禁止跨求解器继承")
    key = cls.version_key(cls.version)
    versions = ADAPTERS.setdefault(cls.name, {})
    for registered in versions.values():
        if registered.version == cls.version:
            raise ConfigurationError("重复 Adapter 版本: " + cls.version)
        if _branch(registered) == _branch(cls) and registered.version_key(registered.version) == key:
            raise ConfigurationError("重复 Adapter 变更点或排序键")
    versions[cls.version] = cls
    return cls


def discover():
    import solvers

    for item in pkgutil.walk_packages(solvers.__path__, prefix="solvers."):
        if item.name.endswith(".adapter") or ".versions." in item.name:
            importlib.import_module(item.name)
    return ADAPTERS


def select(name, actual_version, branch=None):
    discover()
    versions = ADAPTERS.get(name, {})
    if not versions:
        raise UnsupportedCaseError("求解器未注册")
    if branch is None:
        branch = _branch_for_version(name, actual_version)
        if branch is None:
            branches = {_branch(cls) for cls in versions.values()}
            if len(branches) != 1:
                raise UnsupportedCaseError("跨分支选择必须显式指定 branch")
            branch = branches.pop()
    choices = [
        cls
        for cls in versions.values()
        if _branch(cls) == branch and cls.version_key(cls.version) <= cls.version_key(actual_version)
    ]
    if not choices:
        raise UnsupportedCaseError("版本早于最早变更点或求解器未注册")
    return max(choices, key=lambda cls: cls.version_key(cls.version))()


def compatibility(condition, adapter):
    if condition in (None, "*"):
        return True, 0
    if not isinstance(condition, str):
        raise ConfigurationError("compatibility 必须为字符串")
    tokens = re.split(r"\s*,\s*|\s+(?=[<>])", condition.strip())
    bounds = set()
    valid = True
    for token in tokens:
        match = re.fullmatch(r"(>=|<=|>|<|==)?\s*([A-Za-z0-9_.-]+)", token)
        if not match:
            raise ConfigurationError("非法 compatibility: " + condition)
        op, version = match.groups()
        op = op or "=="
        if version not in {cls.version for cls in _classes(adapter.name, _branch(adapter))}:
            if version in ADAPTERS.get(adapter.name, {}):
                return False, 0
            raise ConfigurationError("compatibility 引用未注册变更点: " + version)
        actual = adapter.version_key(adapter.version)
        required = adapter.version_key(version)
        if op == "==":
            valid &= adapter.version == version
            bounds.add("exact")
        elif op in (">", ">="):
            if op == ">":
                valid &= actual > required
            else:
                valid &= actual >= required
            bounds.add("lower")
        else:
            if op == "<":
                valid &= actual < required
            else:
                valid &= actual <= required
            bounds.add("upper")
    if "exact" in bounds:
        priority = 3
    elif {"lower", "upper"} <= bounds:
        priority = 2
    else:
        priority = 1
    return bool(valid), priority


def mapped(declaration, canonical, adapter):
    matches = []
    for item in declaration.get("mapping", []):
        if item["solver"] == adapter.name and compatibility(item.get("compatibility", "*"), adapter)[0]:
            matches.append(item)
    if len(matches) > 1:
        raise ConfigurationError("多个同时匹配的 mapping: " + canonical)
    if not matches:
        return canonical, declaration.get("unit", "")
    return matches[0]["name"], matches[0].get("unit", declaration.get("unit", ""))


def version_key(name, version, branch=None):
    """使用已注册内核的版本规则返回排序键，不读取或探测本机安装。"""
    discover()
    versions = ADAPTERS.get(name, {})
    if not versions:
        raise UnsupportedCaseError("未注册求解器: " + name)
    if branch is None:
        branch = _branch_for_version(name, version)
        if branch is None:
            branches = {_branch(cls) for cls in versions.values()}
            if len(branches) != 1:
                raise UnsupportedCaseError("跨分支版本排序必须显式指定 branch")
            branch = branches.pop()
    classes = _classes(name, branch)
    if not classes:
        raise UnsupportedCaseError("分支未注册: " + branch)
    public = min(classes, key=lambda cls: cls.version_key(cls.version))
    return public.version_key(version)


def load_env(installation):
    """根据安装配置返回独立环境变量字典；配置非法或加载失败时抛出配置或准备异常。"""
    spec = installation.get("environment", {"kind": "existing"})
    kind = spec.get("kind")
    base = dict(os.environ)
    if kind == "existing":
        if "modules" in spec or "script" in spec:
            raise ConfigurationError("existing 不允许模块或脚本参数")
        environment = base
    elif kind == "script":
        if "modules" in spec:
            raise ConfigurationError("script 不允许 modules")
        script = spec.get("script")
        if not isinstance(script, str) or not Path(script).is_file():
            raise ConfigurationError("环境脚本不存在")
        argv = ["bash", "-c", "source " + shlex.quote(script) + " >/dev/null || exit $?; env -0"]
        with tempfile.TemporaryFile() as captured:
            result = subprocess.run(
                argv, stdout=captured, stderr=subprocess.PIPE, env=base, timeout=30
            )
            captured.seek(0)
            stdout = captured.read()
        if result.returncode:
            raise PreprocessError("环境加载失败: " + result.stderr.decode("utf-8", "replace")[-2000:])
        environment = {}
        for pair in stdout.split(b"\0"):
            if b"=" in pair:
                key, value = pair.split(b"=", 1)
                environment[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    elif kind == "module":
        if "script" in spec:
            raise ConfigurationError("module 不允许 script")
        modules = spec.get("modules")
        if (
            not isinstance(modules, list)
            or not modules
            or not all(isinstance(m, str) and m and not m.startswith("-") for m in modules)
        ):
            raise ConfigurationError("非法模块参数")
        argv = ["bash", "-lc", 'module load "$@" >/dev/null || exit $?; env -0', "simtest"] + modules
        with tempfile.TemporaryFile() as captured:
            result = subprocess.run(
                argv, stdout=captured, stderr=subprocess.PIPE, env=base, timeout=30
            )
            captured.seek(0)
            stdout = captured.read()
        if result.returncode:
            raise PreprocessError("环境加载失败: " + result.stderr.decode("utf-8", "replace")[-2000:])
        environment = {}
        for pair in stdout.split(b"\0"):
            if b"=" in pair:
                key, value = pair.split(b"=", 1)
                environment[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    else:
        raise ConfigurationError("未知 environment.kind")
    environment["OMP_NUM_THREADS"] = "1"
    prepend = installation.get("path_prepend", [])
    if not isinstance(prepend, list) or not all(isinstance(item, str) and item for item in prepend):
        raise ConfigurationError("path_prepend 必须为非空字符串列表")
    if prepend:
        existing = environment.get("PATH", "")
        environment["PATH"] = os.pathsep.join(prepend + ([existing] if existing else []))
    return environment


def register_install(root, args):
    """按 CLI 参数探测已有安装并原子写入配置；返回配置路径和版本信息，配置冲突时抛出配置或版本异常。"""
    discover()

    if args.solver not in ADAPTERS:
        raise ConfigurationError("求解器没有注册")
    path = Path(args.path).resolve()
    if not path.is_dir():
        raise ConfigurationError("安装根目录不存在")
    environment = {"kind": args.environment}
    if args.environment_script:
        environment["script"] = str(Path(args.environment_script).resolve())
    if args.environment_module:
        environment["modules"] = args.environment_module
    installation = {"solver": args.solver, "version": args.version, "path": str(path), "environment": environment}
    prepend = getattr(args, "path_prepend", None)
    if prepend:
        installation["path_prepend"] = list(prepend)
    activated = load_env(installation)
    candidates = [cls for cls in ADAPTERS[args.solver].values() if cls.version == str(args.version)]
    if not candidates:
        raise VersionMismatchError("配置版本没有注册 Adapter: " + str(args.version))
    public = candidates[0]()
    info = public.probe(SimpleNamespace(environment=activated))
    if info.version != args.version:
        raise VersionMismatchError("配置 %s 与真实 %s 不一致" % (args.version, info.version))
    branch = getattr(public, "branch", "")
    if branch:
        installation["branch"] = branch
    try:
        public.check_installation(info, path)
    except VersionMismatchError as exc:
        raise ConfigurationError("激活后的求解器不属于 --path 指定的安装") from exc
    select(args.solver, info.version, branch or None)

    if args.config:
        file = Path(args.config).resolve()
    else:
        file = root / "config.yaml"
    if file.exists():
        config = read_yaml(file)
    else:
        config = {"installations": []}

    if not isinstance(config.get("installations"), list):
        raise ConfigurationError("config.installations 必须为列表")
    existing = [
        item
        for item in config["installations"]
        if (item.get("solver"), str(item.get("version"))) == (args.solver, args.version)
    ]
    if len(existing) > 1:
        raise ConfigurationError("部署配置有重复安装记录")
    if existing and not args.force:
        raise ConfigurationError("安装已登记；替换需使用 --force")
    config["installations"] = [item for item in config["installations"] if item not in existing] + [installation]
    import yaml

    atomic_text(file, yaml.safe_dump(config, allow_unicode=True, sort_keys=False))

    ignore = root / ".gitignore"
    if ignore.exists():
        content = ignore.read_text()
    else:
        content = ""
    if "config.yaml" not in content.splitlines():
        atomic_text(ignore, content.rstrip() + "\nconfig.yaml\n")
    return {"config": str(file), "solver": info.__dict__}


def select_install(root, selector, config_file=None):
    """按名称和版本选择安装，返回安装、环境、实际版本及 Adapter；缺失、不兼容或歧义时抛出异常。"""
    discover()

    name, sep, requested = selector.partition("@")
    requested = requested if sep else "latest"
    if name not in ADAPTERS:
        raise UnsupportedCaseError("未注册求解器: " + name)

    if config_file:
        config_path = Path(config_file)
    else:
        config_path = root / "config.yaml"
    config = read_yaml(config_path)
    installations = [
        entry
        for entry in config.get("installations", [])
        if entry.get("solver") == name and (requested == "latest" or str(entry.get("version")) == requested)
    ]
    if not installations:
        raise ConfigurationError("没有匹配安装，请先 simtest setup")

    found = []
    branches = set()
    for installation in installations:
        branch = installation.get("branch")
        if branch is None:
            branch = _branch_for_version(name, installation["version"])
        if branch is None:
            known = {_branch(cls) for cls in ADAPTERS[name].values()}
            if len(known) == 1:
                branch = known.pop()
        if branch is None:
            raise ConfigurationError("安装缺少 branch，且版本未注册: " + str(installation["version"]))
        classes = _classes(name, branch)
        if not classes:
            raise ConfigurationError("安装分支没有注册 Adapter: " + branch)
        public = min(classes, key=lambda cls: cls.version_key(cls.version))()
        env = load_env(installation)
        info = public.probe(SimpleNamespace(environment=env))
        if info.version != str(installation["version"]):
            raise VersionMismatchError("部署版本与探测版本不一致")
        expected_branch = getattr(public, "branch", "")
        if expected_branch and getattr(info, "branch", "") != expected_branch:
            raise VersionMismatchError("部署分支与探测分支不一致")
        public.check_installation(info, installation["path"])
        found.append((public.version_key(info.version), branch, installation, env, info))
        branches.add(branch)

    if requested == "latest" and len(branches) > 1:
        raise ConfigurationError("跨分支 latest 歧义，请显式指定版本")
    found.sort(key=lambda item: item[0], reverse=True)
    if len(found) > 1 and found[0][0] == found[1][0]:
        raise ConfigurationError("latest 对应多个同版本安装，请消除部署歧义")
    _, branch, installation, env, info = found[0]
    return installation, env, info, select(name, info.version, branch or None)
