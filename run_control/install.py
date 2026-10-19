"""本机已有求解器的安装登记、实际版本校验和安装选择。"""

from pathlib import Path
from types import SimpleNamespace

from common.io import atomic_text, read_yaml
from run_control.environment import load_env
from solvers.exceptions import ConfigurationError, UnsupportedCaseError, VersionMismatchError
from solvers.registry import ADAPTERS, discover, select


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
    activated = load_env(installation)
    public = min(ADAPTERS[args.solver].values(), key=lambda cls: cls.version_key(cls.version))()
    info = public.probe(SimpleNamespace(environment=activated))
    if info.version != args.version:
        raise VersionMismatchError("配置 %s 与真实 %s 不一致" % (args.version, info.version))
    if path not in Path(info.executables["icoFoam"]).parents:
        raise ConfigurationError("激活后的求解器不属于 --path 指定的安装")
    select(args.solver, info.version)

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
    public = min(ADAPTERS[name].values(), key=lambda cls: cls.version_key(cls.version))()
    for installation in installations:
        env = load_env(installation)
        info = public.probe(SimpleNamespace(environment=env))
        if info.version != str(installation["version"]):
            raise VersionMismatchError("部署版本与探测版本不一致")
        actual_path = Path(info.executables["icoFoam"]).resolve()
        if Path(installation["path"]).resolve() not in actual_path.parents:
            raise VersionMismatchError("当前环境使用了另一安装的可执行文件")
        found.append((public.version_key(info.version), installation, env, info))

    found.sort(key=lambda item: item[0], reverse=True)
    if len(found) > 1 and found[0][0] == found[1][0]:
        raise ConfigurationError("latest 对应多个同版本安装，请消除部署歧义")
    _, installation, env, info = found[0]
    return installation, env, info, select(name, info.version)
