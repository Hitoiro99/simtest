"""Generate reusable offline reports from archived observations and terminal failure diagnostics."""

from collections import OrderedDict
import hashlib
from pathlib import Path
import shutil
from types import SimpleNamespace
import csv
import datetime
import html
from importlib import resources
import json
import math
import os
from urllib.parse import quote
import uuid

from analysis import field_comparisons, monitor_comparisons
from archive import load_observations, verify_archive
from common.io import atomic_json, atomic_text, identifier, inventory, json_safe, sha256
from solvers.base import redact
from solvers.exceptions import ConfigurationError, PostprocessError
from solvers.registry import version_key


def report_sources(root, case_id, job_ids=None):
    """Load selected terminal jobs, deriving observations from archived CSV/VTU."""
    requested = set(job_ids or [])
    for job_id in requested:
        identifier(job_id)
    found = {}
    artifacts = root / "artifacts" / case_id
    for file in sorted((artifacts / "runs").glob("*/*/*/*/manifest.json")):
        if requested and file.parent.name not in requested:
            continue
        verify_archive(file.parent)
        manifest = json.loads(file.read_text(encoding="utf-8"))
        status = json.loads((file.parent / "status.json").read_text(encoding="utf-8"))
        if status["status"] != "SUCCEEDED":
            raise PostprocessError("正式归档不是成功作业: " + str(file.parent))
        observations = load_observations(file.parent, manifest)
        manifest["monitors"] = observations["monitors"]
        context = SimpleNamespace(case=manifest["case"], condition=manifest["condition"], manifest=manifest)
        manifest["comparisons"] = {
            "monitors": monitor_comparisons(context),
            "fields": field_comparisons(context, observations["fields"]),
        }
        found[manifest["job_id"]] = (file.parent, manifest, status)
    failures = {"UNSUPPORTED", "TIMEOUT", "CRASHED", "INFRA_ERROR", "CANCELLED"}
    for file in sorted((root / "runs").glob("*/manifest.json")):
        job_id = file.parent.name
        if (requested and job_id not in requested) or job_id in found:
            continue
        manifest = json.loads(file.read_text(encoding="utf-8"))
        identity_case = manifest.get("identity", {}).get("case")
        if manifest.get("case", {}).get("id", identity_case) != case_id:
            continue
        status = json.loads((file.parent / "status.json").read_text(encoding="utf-8"))
        if status["status"] not in failures:
            if job_id in requested:
                raise ConfigurationError("报告作业尚未归档或未进入失败终态: " + job_id)
            continue
        manifest["monitors"] = {}
        manifest["comparisons"] = {"monitors": [], "fields": []}
        status["diagnostics"] = json_safe(status.get("diagnostics", []))
        status["log_summary"] = []
        for log in sorted((file.parent / "logs").glob("*.log")):
            if log.is_symlink():
                raise PostprocessError("失败日志不允许符号链接")
            with log.open("rb") as stream:
                stream.seek(max(0, log.stat().st_size - 4096))
                tail = stream.read().decode("utf-8", "replace")
            status["log_summary"].append({"file": log.name, "tail": redact(tail)})
        status["diagnostics"] = [redact(str(item)) for item in status["diagnostics"]]
        found[job_id] = (file.parent, manifest, status)
    if requested and set(found) != requested:
        raise ConfigurationError("请求的报告作业不存在或尚未进入终态")
    if not found:
        raise ConfigurationError("没有成功归档或终态失败作业可生成报告；prepare-only 作业不生成报告。")
    return [found[job_id] for job_id in sorted(found)]


def report_digest(value):
    encoded = json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def report(root, case_id, job_ids=None):
    """Atomically create or reuse a verified offline report for terminal jobs."""
    identifier(case_id)
    runs = report_sources(root, case_id, job_ids)
    code = {name: sha256(Path(__file__).with_name(name)) for name in ("report.py", "analysis.py")}
    for name in ("report.js", "report.css"):
        if hasattr(resources, "files"):
            content = resources.files("report_assets").joinpath(name).read_bytes()
        else:
            content = resources.read_binary("report_assets", name)
        code[name] = hashlib.sha256(content).hexdigest()
    identities = []
    for path, manifest, status in runs:
        identities.append({"job_id": manifest["job_id"], "manifest": manifest, "status": status})
    report_id = report_digest({"schema": 1, "case": case_id, "jobs": identities, "code": code})
    reports = root / "artifacts" / case_id / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    destination = reports / report_id
    import fcntl

    with (reports / ".lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if destination.exists():
                try:
                    expected = json.loads((destination / "integrity.json").read_text(encoding="utf-8"))
                    actual = inventory(destination)
                    actual.pop("integrity.json", None)
                    if expected["report_id"] != report_id or actual != expected["files"]:
                        raise ValueError("报告文件清单或哈希不符")
                except (OSError, ValueError, KeyError) as exc:
                    raise PostprocessError("拒绝复用或覆盖损坏报告: " + str(destination)) from exc
                return {"report": str(destination / "report.html"), "runs": len(runs), "reused": True}
            staging = reports / ("." + report_id + ".staging-" + uuid.uuid4().hex)
            staging.mkdir()
            try:
                write_report(staging, case_id, runs)
                atomic_json(staging / "integrity.json", {"report_id": report_id, "files": inventory(staging)})
                staging.rename(destination)
            except BaseException:
                shutil.rmtree(staging)
                raise
            return {"report": str(destination / "report.html"), "runs": len(runs), "reused": False}
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def write_report(destination, case_id, runs):
    created = datetime.datetime.now(datetime.timezone.utc)
    charts = build_charts(runs)
    figures = static_figures(destination, charts)
    rows = monitor_rows(case_id, runs)
    columns = [
        "job_id", "case", "condition", "monitor", "solver", "version", "processes", "last_step", "last_time",
        "last_value", "reference_id", "reference_value", "absolute_error", "normalized_error_percent",
        "comparison_status", "unit", "run_status",
    ]
    with (destination / "summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "case": case_id,
        "created": created.isoformat(),
        "report_format": "html",
        "runs": [{"archive": str(p), "manifest": m, "status": s} for p, m, s in runs],
    }
    atomic_json(destination / "summary.json", summary)
    atomic_text(
        destination / "report.html", render_html(case_id, created.isoformat(), runs, charts, rows, figures, destination)
    )


def number(value):
    try:
        value = float(value)
        if math.isfinite(value):
            return value
        return None
    except (ValueError, TypeError, OverflowError):
        return None


def label(manifest):
    info = manifest["actual_solver"]
    execution = manifest["execution"]
    return "%s / %s / %s / %s × %s · %s" % (
        info["name"],
        info["version"],
        manifest["identity"]["condition"],
        execution["backend"],
        execution["processes"],
        manifest["job_id"][:8],
    )


def build_charts(runs):
    charts = OrderedDict()
    runs = [(path, manifest, status) for path, manifest, status in runs if status["status"] == "SUCCEEDED"]
    latest = {}
    for path, m, status in runs:
        key = (m["identity"]["condition"], m["actual_solver"]["name"])
        candidate = version_key(m["actual_solver"]["name"], m["actual_solver"]["version"])
        if key not in latest or candidate > latest[key]:
            latest[key] = candidate
    for path, m, status in runs:
        condition = m["identity"]["condition"]
        candidate = version_key(m["actual_solver"]["name"], m["actual_solver"]["version"])
        if candidate != latest[(condition, m["actual_solver"]["name"])]:
            continue
        for name, records in m.get("monitors", {}).items():
            declaration = m["case"]["monitors"].get(name, {})
            unit = declaration.get("unit", "1")
            # Never mix physical times and step numbers on one axis.
            for axis in ("time", "step"):
                selected = [r for r in records if (r.get("time") is not None) == (axis == "time")]
                if not selected:
                    continue
                key = ("monitor", name, unit, axis)
                if axis == "time":
                    xlabel = "Physical time [s]"
                else:
                    xlabel = "Step"
                chart = charts.setdefault(
                    key,
                    {
                        "kind": "monitor",
                        "title": name,
                        "description": declaration.get("display_name", name),
                        "unit": unit,
                        "xlabel": xlabel,
                        "ylabel": name + " [" + unit + "]",
                        "series": [],
                    },
                )
                points = []
                for record in selected:
                    x = number(record[axis])
                    if record.get("quality") != "invalid":
                        y = number(record["value"])
                    else:
                        y = None
                    points.append(
                        {
                            "x": x,
                            "y": y,
                            "raw": record["value"],
                            "step": record["step"],
                            "quality": record.get("quality", "valid"),
                        }
                    )
                chart["series"].append({"label": label(m), "job_id": m["job_id"], "points": points})
                for comparison in m.get("comparisons", {}).get("monitors", []):
                    value = number(comparison.get("reference_value"))
                    xs = [p["x"] for p in points if p["x"] is not None]
                    if comparison["monitor"] == name and value is not None and xs:
                        chart["series"].append(
                            {
                                "label": label(m) + " / reference " + comparison["reference_id"],
                                "job_id": m["job_id"],
                                "reference": True,
                                "points": [{"x": x, "y": value, "raw": value} for x in (min(xs), max(xs))],
                            }
                        )
        for row in m.get("comparisons", {}).get("fields", []):
            # Domain/field/reference/condition/unit define independent comparisons.
            key = ("field", condition, row["domain"], row["field"], row["reference_id"], row.get("unit", "1"))
            chart = charts.setdefault(
                key,
                {
                    "kind": "field",
                    "title": " / ".join(key[1:5]),
                    "description": "按实际保存时刻比较；均值和 RMS 按单元体积加权。",
                    "unit": key[5],
                    "xlabel": "Physical time [s]",
                    "ylabel": "Maximum normalized error [%]",
                    "series": [],
                },
            )
            series_label = label(m) + " / " + row["component"]
            series = next((s for s in chart["series"] if s["label"] == series_label), None)
            if series is None:
                series = {"label": series_label, "job_id": m["job_id"], "points": []}
                chart["series"].append(series)
            metrics = {}
            for kind in ("normalized_error", "absolute_error"):
                for metric in ("max", "mean", "rms"):
                    if row["status"] == "AVAILABLE":
                        value = number((row.get(kind) or {}).get(metric))
                    else:
                        value = None
                    if value is not None:
                        if kind == "normalized_error":
                            factor = 100
                        else:
                            factor = 1
                        metric_value = value * factor
                    else:
                        metric_value = None
                    metrics[kind + "." + metric] = metric_value
            series["points"].append(
                {
                    "x": number(row["time"]),
                    "y": metrics["normalized_error.max"],
                    "raw": row.get("reason") or row["status"],
                    "quality": row["status"],
                    "metrics": metrics,
                }
            )
    result = list(charts.values())
    for index, chart in enumerate(result):
        chart["id"] = "chart-%02d" % (index + 1)
        for series in chart["series"]:
            series["points"].sort(key=lambda p: p["x"] if p["x"] is not None else float("inf"))
    return result


def monitor_rows(case_id, runs):
    rows = []
    for path, m, status in runs:
        for name, records in m.get("monitors", {}).items():
            if records:
                last = max(records, key=lambda r: (r["step"], r.get("time") or 0))
            else:
                last = {}
            comparisons = [r for r in m.get("comparisons", {}).get("monitors", []) if r["monitor"] == name] or [{}]
            for comparison in comparisons:
                error = number(comparison.get("normalized_error"))
                rows.append(
                    {
                        "job_id": m["job_id"],
                        "case": case_id,
                        "condition": m["identity"]["condition"],
                        "monitor": name,
                        "solver": m["actual_solver"]["name"],
                        "version": m["actual_solver"]["version"],
                        "processes": m["execution"]["processes"],
                        "last_step": last.get("step"),
                        "last_time": last.get("time"),
                        "last_value": last.get("value"),
                        "reference_id": comparison.get("reference_id"),
                        "reference_value": comparison.get("reference_value"),
                        "absolute_error": comparison.get("absolute_error"),
                        "normalized_error_percent": error * 100 if error is not None else None,
                        "comparison_status": comparison.get("status", "NO_REFERENCE"),
                        "unit": m["case"]["monitors"][name].get("unit", "1"),
                        "run_status": status["status"],
                    }
                )
    return rows


def static_figures(destination, charts):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    figures = destination / "figures"
    figures.mkdir()
    result = []
    for chart in charts:
        fig, ax = plt.subplots(figsize=(10, 5.5))
        for series in chart["series"]:
            ax.plot(
                [p["x"] for p in series["points"]],
                [p["y"] for p in series["points"]],
                label=series["label"],
                linewidth=1.2,
                linestyle="--" if series.get("reference") else "-",
            )
        values = [p["y"] for s in chart["series"] for p in s["points"] if p["y"] is not None]
        if values:
            lo, hi = min(values), max(values)
            minimum = max(abs(lo), abs(hi)) * 0.1 or 1
            if hi - lo < minimum:
                ax.set_ylim((lo + hi - minimum) / 2, (lo + hi + minimum) / 2)
        ax.set_xlabel(chart["xlabel"])
        ax.set_ylabel(chart["ylabel"])
        ax.grid(alpha=0.25)
        ax.legend(fontsize=6)
        fig.tight_layout()
        for extension in ("png", "svg", "pdf"):
            fig.savefig(str(figures / (chart["id"] + "." + extension)), dpi=160)
        plt.close(fig)
        result.append(chart["id"])
    return result


def escaped(value):
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        value = json.dumps(json_safe(value), ensure_ascii=False)
    return html.escape(str(value), quote=True)


def table(headers, rows):
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + "".join("<th>" + escaped(h) + "</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join("<td>" + escaped(v) + "</td>" for v in row) + "</tr>" for row in rows)
        + "</tbody></table></div>"
    )


def render_html(case_id, created, runs, charts, rows, figures, destination):
    if hasattr(resources, "files"):
        assets = resources.files("report_assets")
        css = assets.joinpath("report.css").read_text(encoding="utf-8")
        js = assets.joinpath("report.js").read_text(encoding="utf-8")
    else:
        css = resources.read_text("report_assets", "report.css", encoding="utf-8")
        js = resources.read_text("report_assets", "report.js", encoding="utf-8")
    # A literal </script> in archived text must never close the JSON data block.
    payload = (
        json.dumps(json_safe(charts), ensure_ascii=False, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    job_rows, diagnostics, sources, field_rows = [], [], [], []
    for path, m, status in runs:
        measured = m.get("execution_result", {})
        memory = number(measured.get("peak_memory_bytes"))
        job_rows.append(
            [
                m["job_id"],
                m["identity"]["condition"],
                m["actual_solver"]["name"] + " / " + m["actual_solver"]["version"],
                m["execution"]["processes"],
                status["status"],
                measured.get("wall_seconds"),
                measured.get("cpu_seconds"),
                memory / 1024**2 if memory is not None else None,
            ]
        )
        for diagnostic in status.get("diagnostics", []):
            diagnostics.append("<pre>" + escaped(m["job_id"]) + "\n" + escaped(diagnostic) + "</pre>")
        for log in status.get("log_summary", []):
            diagnostics.append("<pre>" + escaped(m["job_id"] + " / " + log["file"]) + "\n" + escaped(log["tail"]) + "</pre>")
        for ref_id, reference in m.get("condition", {}).get("references", {}).items():
            source = reference.get("source")
            link = ""
            if isinstance(source, dict) and isinstance(source.get("file"), str):
                base = (path / "input" / "_source").resolve()
                source_path = (base / source["file"]).resolve()
                try:
                    source_path.relative_to(base)
                    relative = os.path.relpath(str(source_path), str(destination)).replace(os.sep, "/")
                    link = '<a href="' + escaped(quote(relative, safe="/")) + '">归档来源文件</a>'
                except ValueError:
                    pass
            sources.append(
                "<details><summary>"
                + escaped(m["job_id"] + " / " + ref_id)
                + "</summary>"
                + link
                + "<pre>"
                + escaped(reference)
                + "</pre></details>"
            )
        for row in m.get("comparisons", {}).get("fields", []):
            a, n = row.get("absolute_error") or {}, row.get("normalized_error") or {}
            percent = [number(n.get(metric)) for metric in ("max", "mean", "rms")]
            field_rows.append(
                [
                    m["job_id"],
                    m["identity"]["condition"],
                    row["domain"],
                    row["field"],
                    row["reference_id"],
                    row["component"],
                    row["time"],
                    row.get("unit"),
                    a.get("max"),
                    a.get("mean"),
                    a.get("rms"),
                    *[v * 100 if v is not None else None for v in percent],
                    a.get("max_position"),
                    row["status"],
                    row.get("reason"),
                ]
            )
    parts = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>" + escaped(case_id) + " · 仿真测试报告</title><style>" + css + "</style></head><body>",
        '<header><div class="eyebrow">SIMTEST / VERIFIED ARCHIVES</div><h1>' + escaped(case_id) + "</h1>",
        "<p>仿真测试报告 · " + escaped(created) + " · " + str(len(runs)) + " 个作业</p>",
        '<nav><a href="#jobs">作业状态</a><a href="#charts">交互图表</a><a href="#observations">数值明细</a><a href="#sources">参考与下载</a></nav></header><main>',
        '<div class="notice">SUCCEEDED 表示执行和必需结果完整，不代表收敛或数值通过。报告不设置验收阈值；归一化尺度不是容差。</div>',
        '<section id="jobs"><h2>作业状态</h2><p>成功作业已校验归档及标准结果；失败作业显示保留现场的状态和日志摘要。耗时仅反映各次运行环境，不据此判断跨硬件性能回归。</p>',
        table(
            ["作业 ID", "工况", "求解器 / 实际版本", "进程数", "状态", "墙钟 / s", "CPU / s", "峰值内存 / MiB"],
            job_rows,
        ),
        "<details><summary>诊断记录（"
        + str(len(diagnostics))
        + "）</summary>"
        + ("".join(diagnostics) or "<p>无诊断记录。</p>")
        + "</details></section>",
        '<section id="charts"><h2>交互图表</h2><p>滚轮缩放，拖动框选；切换“平移”后拖动。双击或“重置”恢复，点击图例显隐曲线。支持触屏单指操作和按钮缩放。</p>',
        "<p>曲线使用各工况 / 求解器所选作业中的最新实际版本；状态和明细保留全部所选作业。保留全部采样点；无效值显示为断点，不平滑、不插值、不补值。零值在对数轴不可显示，可切回线性轴。</p>",
        '<div id="chart-list"></div><noscript><p>交互功能需要启用 JavaScript；静态图和以下表格仍可阅读。</p>',
    ]
    for chart in charts:
        parts.append(
            '<img class="static-chart" alt="' + escaped(chart["title"]) + '" src="figures/' + chart["id"] + '.png">'
        )
    parts += [
        '</noscript></section><section id="observations"><h2>数值明细</h2><label>筛选明细 <input id="table-filter" type="search" placeholder="作业 ID、字段、分量或状态" /></label>',
        "<h3>监控最后记录</h3><p>最后值无效时保留原值，不回退到更早的有效记录。NO_REFERENCE 表示未定义监控参考值。</p>",
        '<div class="filterable">'
        + table(
            [
                "作业 ID",
                "监控量",
                "最后步",
                "时间 / s",
                "最后值",
                "单位",
                "参考 ID",
                "参考值",
                "绝对误差",
                "归一化误差 / %",
                "比较状态",
            ],
            [
                [
                    r[k]
                    for k in (
                        "job_id",
                        "monitor",
                        "last_step",
                        "last_time",
                        "last_value",
                        "unit",
                        "reference_id",
                        "reference_value",
                        "absolute_error",
                        "normalized_error_percent",
                        "comparison_status",
                    )
                ]
                for r in rows
            ],
        )
        + "</div>",
        "<h3>解析场偏差</h3><p>逐实际输出时刻比较。均值和 RMS 按单元体积加权；模长误差为两个模长之差的绝对值。— 表示不可用或未提供，不代表零。</p>",
        '<div class="filterable">'
        + table(
            [
                "作业 ID",
                "工况",
                "域",
                "字段",
                "参考 ID",
                "分量",
                "时间 / s",
                "单位",
                "最大绝对误差",
                "平均绝对误差",
                "RMS 绝对误差",
                "最大归一化 / %",
                "平均归一化 / %",
                "RMS 归一化 / %",
                "最大误差位置 / m",
                "状态",
                "原因",
            ],
            field_rows,
        )
        + "</div></section>",
        '<section id="sources"><h2>参考与下载</h2><p><a href="summary.json" download>完整元数据 JSON</a> · <a href="summary.csv" download>监控汇总 CSV</a></p>',
        "<p>图表和数据内嵌于本 HTML，可离线交互。来源链接、CSV / JSON 和静态导出需保留同目录文件及相对归档路径。</p>",
        "".join(sources),
    ]
    for chart in charts:
        parts.append(
            "<p>"
            + escaped(chart["title"])
            + "："
            + " · ".join(
                '<a href="figures/' + chart["id"] + "." + ext + '" download>' + ext.upper() + "</a>"
                for ext in ("png", "svg", "pdf")
            )
            + "</p>"
        )
    parts += [
        "</section></main><footer>SIMTEST · 全量记录 / 可追溯归档 / 离线报告</footer>",
        '<script id="chart-data" type="application/json">'
        + payload
        + "</script><script>"
        + js
        + "</script></body></html>",
    ]
    return "".join(parts)
