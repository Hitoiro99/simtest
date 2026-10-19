from __future__ import annotations

from pathlib import Path
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from solvers.exceptions import ConfigurationError, PreprocessError, UnsupportedCaseError
from solvers.registry import compatibility
from common.io import identifier, inventory, read_yaml, within


def choose(case_path, adapter):
    templates = {}
    for file in sorted((Path(case_path) / "templates").glob("*/template.yaml")):
        definition = read_yaml(file)
        key = identifier(definition.get("id"))
        if key in templates:
            raise ConfigurationError("重复 template.id: " + key)
        if not isinstance(definition.get("solver"), str):
            raise ConfigurationError("template 缺少 solver")
        if "compatibility" not in definition:
            raise ConfigurationError("template 缺少 compatibility")
        definition["_path"] = file.parent
        templates[key] = definition

    def chain(key, seen=()):
        if key not in templates:
            raise ConfigurationError("extends 指向不存在的模板")
        if key in seen:
            raise ConfigurationError("模板循环继承")
        entry = templates[key]
        parent = entry.get("extends")
        if parent:
            if parent not in templates or templates[parent]["solver"] != entry["solver"]:
                raise ConfigurationError("模板父子 solver 不一致或父模板缺失")
            return chain(parent, seen + (key,)) + [entry]
        return [entry]

    candidates = []
    for key, entry in templates.items():
        chain(key)
        if entry["solver"] == adapter.name:
            matched, priority = compatibility(entry["compatibility"], adapter)
            if matched:
                candidates.append((priority, key))
    if not candidates:
        raise UnsupportedCaseError("没有兼容模板")

    parent_ids = {e["id"] for _, key in candidates for e in chain(key)[:-1]}
    leaves = [(p, k) for p, k in candidates if k not in parent_ids]
    best = max(p for p, k in leaves)
    selected = [k for p, k in leaves if p == best]
    if len(selected) != 1:
        raise ConfigurationError("多个同优先级兼容模板")
    return chain(selected[0])


def template_files(chain, adapter):
    """返回继承叠加后的相对路径到源文件映射；执行公共安全和 Adapter 原生布局校验，不渲染。"""
    merged = {}
    for entry in chain:
        for file in sorted(entry["_path"].rglob("*")):
            if file.is_symlink():
                raise ConfigurationError("模板不允许符号链接")
            if not file.is_file():
                continue
            relative = file.relative_to(entry["_path"])
            if relative.as_posix() == "template.yaml":
                continue
            if any(part in ("mesh.cgns", "mesh.msh", "polyMesh") for part in relative.parts):
                raise ConfigurationError("模板不能另带网格")
            adapter.validate_template(relative)
            merged[relative] = file

    return merged


def materialize(context, adapter):
    """使用已选 Adapter 的过滤器一次渲染最终模板，仅写入本作业 input 并记录哈希。"""
    chain = choose(context.case_path, adapter)
    merged = template_files(chain, adapter)
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    environment.filters.clear()
    environment.filters.update(adapter.template_filters())
    environment.globals.clear()
    environment.is_safe_callable = lambda obj: False

    values = dict(context.parameters)
    values.update(
        execution=dict(context.execution),
        solver={"name": context.info.name, "version": context.info.version, "adapter_version": adapter.version},
        condition={"id": context.condition_id},
    )

    context.input.mkdir(parents=True, exist_ok=False)
    for relative, file in merged.items():
        target = within(context.input, context.input / relative)
        try:
            content = environment.from_string(file.read_text(encoding="utf-8")).render(values)
        except (TemplateError, UnicodeError, ConfigurationError) as exc:
            raise PreprocessError("模板渲染失败 %s: %s" % (file, exc))
        if "{{" in content or "{%" in content or "{#" in content:
            raise PreprocessError("渲染后仍存在占位符")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    context.manifest["template"] = {
        "id": chain[-1]["id"],
        "compatibility": chain[-1]["compatibility"],
        "chain": [e["id"] for e in chain],
    }
    context.manifest["rendered_sha256"] = inventory(context.input)
