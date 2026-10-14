"""Reports use verified, archived observations; no solver or comparison is rerun."""
import csv
import datetime
import json
import uuid

from solvers.exceptions import ConfigurationError
from .archive import verify_archive
from .io import atomic_json, atomic_text, identifier
from .report_html import build_charts, monitor_rows, render_html, static_figures


def archived_runs(root, case_id=None):
    """List stored jobs without assuming historic absolute paths still exist."""
    if case_id:
        identifier(case_id)
    cases = [root / "artifacts" / case_id] if case_id else sorted((root / "artifacts").glob("*"))
    result = []
    for case in cases:
        for file in sorted((case / "runs").glob("*/*/*/*/manifest.json")):
            manifest = json.loads(file.read_text(encoding="utf-8"))
            status = json.loads((file.parent / "status.json").read_text(encoding="utf-8"))
            result.append({"case": case.name, "job_id": manifest["job_id"],
                           "condition": manifest["identity"]["condition"],
                           "solver": manifest["actual_solver"]["name"],
                           "version": manifest["actual_solver"]["version"],
                           "processes": manifest["execution"]["processes"],
                           "status": status["status"], "created": manifest.get("created"),
                           "archive": str(file.parent)})
    return sorted(result, key=lambda item: (item["created"] or "", item["job_id"]))


def report(root, case_id, job_ids=None):
    identifier(case_id)
    for job_id in job_ids or []:
        identifier(job_id)
    artifacts = root / "artifacts" / case_id
    runs = []
    for file in sorted((artifacts / "runs").glob("*/*/*/*/manifest.json")):
        if job_ids and file.parent.name not in job_ids:
            continue
        verify_archive(file.parent)
        manifest = json.loads(file.read_text(encoding="utf-8"))
        status = json.loads((file.parent / "status.json").read_text(encoding="utf-8"))
        runs.append((file.parent, manifest, status))
    if not runs:
        raise ConfigurationError("没有已归档的作业可生成报告；请用 list runs 查看可用 ID。prepare-only 作业尚未归档。")
    if job_ids and {m["job_id"] for p, m, s in runs} != set(job_ids):
        raise ConfigurationError("请求的报告作业未全部归档；请用 list runs 查看可用 ID")
    created = datetime.datetime.now(datetime.timezone.utc)
    destination = artifacts / "reports" / (created.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True)
    charts = build_charts(runs)
    figures = static_figures(destination, charts)
    rows = monitor_rows(case_id, runs)
    columns = ["job_id", "case", "condition", "monitor", "solver", "version", "processes",
               "last_step", "last_time", "last_value", "reference_id", "reference_value",
               "absolute_error", "normalized_error_percent", "comparison_status", "unit", "run_status"]
    with (destination / "summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    summary = {"case": case_id, "created": created.isoformat(), "report_format": "html",
               "runs": [{"archive": str(p), "manifest": m, "status": s} for p, m, s in runs]}
    atomic_json(destination / "summary.json", summary)
    atomic_text(destination / "report.html", render_html(case_id, created.isoformat(), runs, charts, rows, figures, destination))
    return {"report": str(destination / "report.html"), "runs": len(runs)}
