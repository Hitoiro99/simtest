from __future__ import annotations

import importlib
import pkgutil
import re

from .exceptions import ConfigurationError, UnsupportedCaseError

ADAPTERS = {}


def register_adapter(cls):
    if not isinstance(getattr(cls, "name", None), str) or not isinstance(getattr(cls, "version", None), str):
        raise ConfigurationError("Adapter 缺少 name/version")
    if getattr(cls, "__abstractmethods__", None):
        raise ConfigurationError("Adapter 未实现所有必需接口")
    for parent in cls.__mro__[1:]:
        if hasattr(parent, "name") and parent.name != cls.name:
            raise ConfigurationError("禁止跨求解器继承")
    key = cls.version_key(cls.version)
    versions = ADAPTERS.setdefault(cls.name, {})
    for registered in versions.values():
        if registered.version == cls.version or registered.version_key(registered.version) == key:
            raise ConfigurationError("重复 Adapter 变更点或排序键")
    versions[cls.version] = cls
    return cls


def discover():
    import solvers

    for item in pkgutil.walk_packages(solvers.__path__, prefix="solvers."):
        if item.name.endswith(".adapter") or ".versions." in item.name:
            importlib.import_module(item.name)
    return ADAPTERS


def select(name, actual_version):
    discover()
    versions = ADAPTERS.get(name, {})
    choices = [cls for cls in versions.values() if cls.version_key(cls.version) <= cls.version_key(actual_version)]
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
        if version not in ADAPTERS[adapter.name]:
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
