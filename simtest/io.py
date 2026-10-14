from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path

import yaml

from solvers.exceptions import ConfigurationError


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in result:
                raise ConfigurationError("重复 YAML 键: %s (line %s)" % (key, key_node.start_mark.line + 1))
        except TypeError:
            raise ConfigurationError("YAML 键必须为标量")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read_yaml(path):
    try:
        value = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=UniqueLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError("无法读取 YAML %s: %s" % (path, exc))
    if not isinstance(value, dict):
        raise ConfigurationError("YAML 根节点必须是字典: %s" % path)
    return value


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value): return str(value)
    if isinstance(value, dict): return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [json_safe(v) for v in value]
    if isinstance(value, Path): return str(value)
    return value


def atomic_json(path, value):
    atomic_text(path, json.dumps(json_safe(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def atomic_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".simtest-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, str(path))
    finally:
        if os.path.exists(name): os.unlink(name)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def inventory(path):
    path = Path(path)
    if path.is_symlink(): raise ConfigurationError("不允许目录符号链接: %s" % path)
    result = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink(): raise ConfigurationError("不允许符号链接: %s" % item)
        if item.is_file(): result[item.relative_to(path).as_posix()] = sha256(item)
    return result


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.=+-]*", value):
        raise ConfigurationError("非法标识符: %r" % value)
    if value in (".", ".."): raise ConfigurationError("非法路径标识符")
    return value


def within(base, path):
    base, path = Path(base).resolve(), Path(path).resolve()
    if path != base and base not in path.parents:
        raise ConfigurationError("路径越界: %s" % path)
    return path
