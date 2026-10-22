"""Generate reusable offline reports from archived observations and terminal failure diagnostics."""

from collections import OrderedDict
import copy
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

from jinja2 import Environment, StrictUndefined

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
        source_manifest = copy.deepcopy(manifest)
        observations = load_observations(file.parent, manifest)
        manifest["source_manifest"] = source_manifest
        manifest["field_samples"] = observations["fields"]
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
    for name in ("report.js", "report.css", "report.html", "echarts.min.js",
                 "ECHARTS-LICENSE.txt", "ECHARTS-NOTICE.txt", "ECHARTS-D3-LICENSE.txt", "echarts-version.json"):
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
    for name in ("ECHARTS-LICENSE.txt", "ECHARTS-NOTICE.txt", "ECHARTS-D3-LICENSE.txt"):
        atomic_text(destination / name, asset_text(name))
    write_details(destination, runs)
    atomic_text(
        destination / "report.html", render_html(case_id, created.isoformat(), runs, charts, rows, figures, destination)
    )


def asset_text(name):
    if hasattr(resources, "files"):
        return resources.files("report_assets").joinpath(name).read_text(encoding="utf-8")
    return resources.read_text("report_assets", name, encoding="utf-8")


def detail_records(runs):
    monitors, fields = [], []
    for path, manifest, status in runs:
        for name, records in manifest.get("monitors", {}).items():
            for record in records:
                monitors.append({"job_id": manifest["job_id"], "monitor": name, **record})
        for record in manifest.get("comparisons", {}).get("fields", []):
            fields.append({"job_id": manifest["job_id"], **record})
    return monitors, fields


def write_details(destination, runs):
    """Export every observation and comparison, preserving nested coordinates as JSON."""
    monitors, fields = detail_records(runs)
    for name, records in (("monitors.csv", monitors), ("field_errors.csv", fields)):
        columns = list(dict.fromkeys(key for record in records for key in record))
        if not columns:
            columns = ["job_id"]
        with (destination / name).open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for record in records:
                row = {}
                for key, value in record.items():
                    if isinstance(value, (dict, list)):
                        value = json.dumps(json_safe(value), ensure_ascii=False)
                    row[key] = value
                writer.writerow(row)


def number(value):
    try:
        value = float(value)
        if math.isfinite(value):
            return value
        return None
    except (ValueError, TypeError, OverflowError):
        return None


def condition_name(manifest):
    """Return the condition ID, which is the YAML file stem under conditions/."""
    return manifest["identity"]["condition"]


def execution_label(execution):
    if execution.get("name"):
        return execution["name"]
    processes = execution.get("processes", 1)
    mode = "%d procs" % processes
    backend = execution.get("backend", "serial")
    if backend != "serial":
        mode += " / " + backend
    return mode


def label(manifest):
    info = manifest["actual_solver"]
    return "%s / %s / %s / %s · %s" % (
        info["name"],
        info["version"],
        condition_name(manifest),
        execution_label(manifest["execution"]),
        manifest["job_id"][:8],
    )


def field_step(manifest, time_value):
    """Return the verified solver step for an archived field output time."""
    value = number(time_value)
    if value is None:
        return None

    reader_times = manifest.get("field_reader", {}).get("times", [])
    for entry in reader_times:
        if number(entry.get("time")) != value:
            continue
        step = entry.get("provenance", {}).get("step")
        if step is not None:
            return step

    axis = manifest.get("solver_time_axis", {})
    if number(axis.get("start")) == value:
        return 0
    for step, solver_time in enumerate(axis.get("steps", []), start=1):
        if number(solver_time) == value:
            return step

    for records in manifest.get("monitors", {}).values():
        for record in records:
            if number(record.get("time")) == value:
                return record.get("step")
    return None


def is_residual(name, declaration):
    mappings = declaration.get("mapping", [])
    return (
        name.startswith("residual_")
        or declaration.get("type") == "residual"
        or any(
            isinstance(item, dict) and str(item.get("name", "")).startswith("residual:")
            for item in mappings
        )
    )


def build_charts(runs):
    charts = OrderedDict()
    runs = [(path, manifest, status) for path, manifest, status in runs if status["status"] == "SUCCEEDED"]
    has_analytical = any(manifest.get("comparisons", {}).get("fields") for path, manifest, status in runs)
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
            residual = is_residual(name, declaration)
            if has_analytical and not residual:
                continue
            selected = records
            if not selected:
                continue
            kind = "residual" if residual else "monitor"
            key = (kind, name, unit)
            chart = charts.setdefault(
                key,
                {
                    "kind": kind,
                    "title": name,
                    "description": declaration.get("display_name", name),
                    "unit": unit,
                    "xlabel": "Step",
                    "ylabel": name + " [" + unit + "]",
                    "yscale": "log" if residual else "linear",
                    "series": [],
                },
            )
            points = []
            for record in selected:
                x = number(record.get("step"))
                if record.get("quality") != "invalid":
                    y = number(record["value"])
                else:
                    y = None
                points.append(
                    {
                        "x": x,
                        "y": y,
                        "raw": record["value"],
                        "step": record.get("step"),
                        "time": record.get("time"),
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
            error_kind = "normalized_error"
            key = (
                "analytical", condition, row["domain"], row["field"], row["reference_id"],
                row.get("unit", "1"), row["component"],
            )
            chart = charts.setdefault(key, {
                "kind": "analytical",
                "title": " / ".join(
                    (condition_name(m), row["domain"], row["field"], row["component"], "解析解归一化偏差")
                ),
                "description": "按实际保存迭代步比较；均值和 RMS 按单元体积加权。",
                "unit": key[5], "component": row["component"], "error_kind": error_kind,
                "xlabel": "Step", "ylabel": "归一化误差 [%]", "yscale": "linear", "series": [],
            })
            series_label = label(m)
            series = next((s for s in chart["series"] if s["label"] == series_label), None)
            if series is None:
                series = {"label": series_label, "job_id": m["job_id"], "points": []}
                chart["series"].append(series)
            metrics = {}
            for metric in ("max", "mean", "rms"):
                value = None
                if row["status"] == "AVAILABLE":
                    value = number((row.get(error_kind) or {}).get(metric))
                if value is not None:
                    value *= 100
                metrics[error_kind + "." + metric] = value
            step = field_step(m, row.get("time"))
            series["points"].append({
                "x": number(step), "y": metrics[error_kind + ".max"],
                "raw": row.get("reason") or row["status"], "quality": row["status"], "metrics": metrics,
                "step": step, "time": row.get("time"),
            })
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


def final_field_rows(runs):
    """Build report-only final-step analytical summaries without changing archives."""
    rows = []
    for path, manifest, status in runs:
        grouped = {}
        for comparison in manifest.get("comparisons", {}).get("fields", []):
            key = (
                comparison["domain"], comparison["field"], comparison["reference_id"], comparison["component"],
            )
            step = field_step(manifest, comparison.get("time"))
            candidate = (step if step is not None else -1, number(comparison.get("time")) or 0, step, comparison)
            if key not in grouped or candidate[:2] > grouped[key][:2]:
                grouped[key] = candidate
        for candidate in grouped.values():
            step = candidate[2]
            comparison = candidate[3]
            metrics = comparison.get("normalized_error") or {}
            percentages = {}
            for metric in ("max", "mean", "rms"):
                value = number(metrics.get(metric))
                percentages[metric] = value * 100 if value is not None else None
            rows.append(
                {
                    "job_id": manifest["job_id"],
                    "condition": condition_name(manifest),
                    "solver": manifest["actual_solver"]["name"],
                    "version": manifest["actual_solver"]["version"],
                    "domain": comparison["domain"],
                    "field": comparison["field"],
                    "component": comparison["component"],
                    "step": step,
                    "time": comparison.get("time"),
                    "max_percent": percentages["max"],
                    "mean_percent": percentages["mean"],
                    "rms_percent": percentages["rms"],
                    "status": comparison.get("status"),
                }
            )
    return rows


def log_tick_label(value, position):
    return "10^%d" % round(math.log10(value))


def static_figures(destination, charts):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib import font_manager
    from matplotlib import ticker

    candidates = (
        Path("/mnt/c/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/mnt/c/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
    )
    for font in candidates:
        if not font.is_file():
            continue
        name = font_manager.FontProperties(fname=str(font)).get_name()
        if hasattr(font_manager.fontManager, "addfont"):
            font_manager.fontManager.addfont(str(font))
        else:
            from matplotlib.font_manager import FontEntry
            font_manager.fontManager.ttflist.append(FontEntry(fname=str(font), name=name))
        plt.rcParams["font.family"] = name
        break
    # 用 TrueType 子集嵌入，避免 Type3 在 .ttc 上失败
    plt.rcParams["pdf.fonttype"] = 3
    plt.rcParams["axes.unicode_minus"] = False

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
        if chart.get("yscale") == "log":
            ax.set_yscale("log", nonpositive="mask")
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(log_tick_label))
            ax.yaxis.set_minor_formatter(ticker.NullFormatter())
        elif values:
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
    # Escape script delimiters independently of HTML autoescaping for JSON script data.
    payload = json.dumps(json_safe(charts), ensure_ascii=False, allow_nan=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    jobs, details = [], []
    for path, manifest, status in runs:
        measured = manifest.get("execution_result", {})
        jobs.append([
            manifest["job_id"], condition_name(manifest), manifest["actual_solver"]["name"],
            manifest["actual_solver"]["version"], manifest["execution"]["processes"], status["status"],
            measured.get("wall_seconds"), measured.get("cpu_seconds"), measured.get("peak_memory_bytes"),
        ])
        links = []
        for name in sorted(inventory(path)):
            relative = os.path.relpath(str(path / name), str(destination)).replace(os.sep, "/")
            links.append({"name": name, "url": quote(relative, safe="/")})
        details.append({
            "job_id": manifest["job_id"], "condition": condition_name(manifest), "links": links,
            "diagnostics": json.dumps(
                json_safe(
                    {
                        "diagnostics": status.get("diagnostics", []),
                        "log_summary": status.get("log_summary", []),
                    }
                ),
                ensure_ascii=False,
                indent=2,
            ),
        })
    monitor_columns = [
        "job_id", "condition", "monitor", "solver", "version", "processes", "last_step", "last_time",
        "last_value", "reference_id", "reference_value", "normalized_error_percent", "comparison_status", "unit",
        "run_status",
    ]
    field_rows = final_field_rows(runs)
    field_columns = [
        "job_id", "condition", "solver", "version", "domain", "field", "component", "step", "time",
        "max_percent", "mean_percent", "rms_percent", "status",
    ]
    monitor_headers = [
        "作业 ID", "工况", "监控量", "求解器", "版本", "进程数", "最后步", "物理时间", "最后值",
        "参考 ID", "参考值", "归一化误差 / %", "比较状态", "单位", "运行状态",
    ]
    field_headers = [
        "作业 ID", "工况", "求解器", "版本", "域", "场", "分量", "最后步", "物理时间",
        "最大误差 / %", "平均误差 / %", "RMS / %", "状态",
    ]
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    template = environment.from_string(asset_text("report.html"))
    return template.render(
        case_id=case_id, created=created, runs=runs, charts=charts, details=details,
        css=asset_text("report.css"), js=asset_text("report.js"), echarts=asset_text("echarts.min.js"),
        payload=payload,
        jobs_table=table(["作业 ID", "工况", "求解器", "实际版本", "进程数", "状态", "墙钟 / s", "CPU / s", "峰值内存 / byte"], jobs),
        monitors_table=table(monitor_headers, [[row.get(key) for key in monitor_columns] for row in rows]),
        fields_table=table(field_headers, [[row.get(key) for key in field_columns] for row in field_rows]),
    )
