import copy
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from archive import archived_runs, manifest_digest
from simtest import parser
from common.io import atomic_json, inventory
from report import build_charts, field_step, final_field_rows, log_tick_label, monitor_rows, render_html, report
from solvers.exceptions import ConfigurationError, PostprocessError


def fixture():
    return {
        "job_id": "job-a",
        "created": "2026-10-13",
        "identity": {"condition": "Re=10"},
        "actual_solver": {"name": "OpenFOAM", "version": "12"},
        "execution": {"backend": "serial", "processes": 1},
        "case": {"monitors": {"u": {"unit": "m/s"}}},
        "condition": {},
        "solver_time_axis": {"start": 0, "steps": [1, 2]},
        "monitors": {
            "u": [{"step": 0, "time": 0, "value": 1}, {"step": 1, "time": 1, "value": "nan", "quality": "invalid"}]
        },
        "comparisons": {"monitors": [], "fields": []},
    }


def stored_fixture(root, job_id="job-a"):
    path = root / "artifacts/example/runs/Re=10/OpenFOAM/12" / job_id
    path.mkdir(parents=True)
    (path / "input").mkdir()
    (path / "input" / "parameters.txt").write_text("fixed input", encoding="utf-8")
    (path / "logs").mkdir()
    (path / "logs" / "solver.log").write_text("End", encoding="utf-8")
    (path / "normalized").mkdir()
    (path / "normalized" / "monitors.csv").write_text("step,time,u\n0,0,1\n1,1,nan\n", encoding="utf-8")
    atomic_json(path / "status.json", {"status": "SUCCEEDED"})
    manifest = fixture()
    manifest["job_id"] = job_id
    manifest["case"]["id"] = "example"
    manifest["input_sha256"] = inventory(path / "input")
    manifest["fields"] = []
    manifest["archive_integrity"] = {"files": inventory(path), "manifest_content_sha256": manifest_digest(manifest)}
    atomic_json(path / "manifest.json", manifest)
    return path


def report_worker(root, queue):
    try:
        with patch("report.static_figures", return_value=[]):
            queue.put(report(Path(root), "example", ["job-a"]))
    except BaseException as exc:
        queue.put({"error": repr(exc)})


class ReportTests(unittest.TestCase):
    def test_invalid_last_and_sampling_axes_are_preserved(self):
        m = fixture()
        m["monitors"]["u"].append({"step": 2, "time": None, "value": "inf"})
        runs = [(Path("archive"), m, {"status": "SUCCEEDED"})]
        charts = build_charts(runs)
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0]["series"][0]["points"][1]["y"], None)
        self.assertEqual(charts[0]["series"][0]["points"][1]["raw"], "nan")
        self.assertEqual(charts[0]["xlabel"], "Step")
        self.assertEqual([point["x"] for point in charts[0]["series"][0]["points"]], [0, 1, 2])
        self.assertEqual(monitor_rows("example", runs)[0]["last_value"], "inf")

    def test_latest_version_uses_solver_rule_without_installation(self):
        runs = []
        for version in ("2025R2", "2026R1", "2025R1"):
            manifest = fixture()
            manifest["job_id"] = "job-" + version
            manifest["actual_solver"] = {"name": "Fluent", "version": version}
            runs.append((Path("archive"), manifest, {"status": "SUCCEEDED"}))

        def fluent_version(name, version):
            self.assertEqual(name, "Fluent")
            year, release = version.split("R")
            return int(year), int(release)

        with patch("report.version_key", side_effect=fluent_version) as comparator:
            charts = build_charts(runs)
        self.assertTrue(comparator.called)
        self.assertEqual(len(charts), 1)
        self.assertEqual([series["job_id"] for series in charts[0]["series"]], ["job-2026R1"])

    def test_field_comparisons_are_grouped_without_bridging_unavailable(self):
        m = fixture()
        row = {
            "field": "velocity",
            "domain": "fluid",
            "reference_id": "r",
            "component": "x",
            "time": 0,
            "unit": "m/s",
            "status": "AVAILABLE",
            "absolute_error": {"max": 0.2, "mean": 0.1, "rms": 0.15},
            "normalized_error": {"max": 0.02, "mean": 0.01, "rms": 0.015},
        }
        m["comparisons"]["fields"] = [
            row,
            dict(row, time=1, status="UNAVAILABLE", reason="bad field"),
            dict(row, time=2),
            dict(row, domain="solid"),
            dict(row, field="other"),
            dict(row, reference_id="r2"),
        ]
        charts = build_charts([(Path("archive"), m, {"status": "SUCCEEDED"})])
        fields = [chart for chart in charts if chart["kind"] == "analytical"]
        self.assertEqual(len(fields), 4)
        points = fields[0]["series"][0]["points"]
        self.assertEqual([p["y"] for p in points], [2, None, 2])
        self.assertEqual([p["x"] for p in points], [0, 1, 2])
        self.assertEqual(points[0]["metrics"]["normalized_error.mean"], 1)
        self.assertNotIn("absolute_error.mean", points[0]["metrics"])
        self.assertFalse(any(chart["kind"] == "monitor" for chart in charts))

    def test_components_and_error_types_have_independent_charts(self):
        manifest = fixture()
        manifest["comparisons"]["fields"] = [
            {"domain": "fluid", "field": "velocity", "component": component, "reference_id": "r",
             "time": 0, "unit": "m/s", "status": "AVAILABLE",
             "absolute_error": {"max": 1}, "normalized_error": {"max": 0.1}}
            for component in ("x", "y", "z", "magnitude")
        ]
        charts = build_charts([(Path("archive"), manifest, {"status": "SUCCEEDED"})])
        fields = [chart for chart in charts if chart["kind"] == "analytical"]
        self.assertEqual(len(fields), 4)
        self.assertEqual({(chart["component"], chart["error_kind"]) for chart in fields},
                         {(component, "normalized_error") for component in ("x", "y", "z", "magnitude")})
        self.assertFalse(any(chart["kind"] == "monitor" for chart in charts))

    def test_field_step_uses_verified_time_metadata_and_final_summary(self):
        manifest = fixture()
        manifest["field_reader"] = {
            "times": [
                {"time": 0, "provenance": {"kind": "native_controlDict_startTime"}},
                {"time": 1, "provenance": {"kind": "native_time_dictionary", "step": 100}},
            ]
        }
        comparison = {
            "domain": "fluid", "field": "velocity", "component": "x", "reference_id": "r", "time": 1,
            "unit": "m/s", "status": "AVAILABLE", "absolute_error": {"max": 0.2},
            "normalized_error": {"max": 0.02, "mean": 0.01, "rms": 0.015},
        }
        manifest["comparisons"]["fields"] = [comparison]
        runs = [(Path("archive"), manifest, {"status": "SUCCEEDED"})]
        self.assertEqual(field_step(manifest, 1), 100)
        row = final_field_rows(runs)[0]
        self.assertEqual(row["step"], 100)
        self.assertEqual(row["max_percent"], 2)
        self.assertNotIn("absolute_error", row)

    def test_residual_has_step_axis_log_default_and_nonpositive_raw_data(self):
        manifest = fixture()
        manifest["case"]["monitors"] = {"residual_p": {"unit": "1"}}
        manifest["monitors"] = {"residual_p": [
            {"step": 1, "time": 0.001, "value": 1e-4},
            {"step": 2, "time": 0.002, "value": 0},
            {"step": 3, "time": 0.003, "value": -1},
        ]}
        chart = build_charts([(Path("archive"), manifest, {"status": "SUCCEEDED"})])[0]
        self.assertEqual(chart["kind"], "residual")
        self.assertEqual(chart["yscale"], "log")
        self.assertEqual([point["x"] for point in chart["series"][0]["points"]], [1, 2, 3])
        self.assertEqual([point["raw"] for point in chart["series"][0]["points"]], [1e-4, 0, -1])
        self.assertIn("Re=10", chart["series"][0]["label"])

    def test_log_tick_label_uses_ascii_minus(self):
        self.assertEqual(log_tick_label(1e-3, None), "10^-3")

    def test_html_is_offline_and_escapes_archived_text(self):
        m = fixture()
        malicious = '</script><script>alert("injected")</script>'
        m["case"]["monitors"]["u"]["display_name"] = malicious
        status = {"status": "CRASHED", "diagnostics": [malicious]}
        runs = [(Path("archive"), m, status)]
        charts = build_charts([(Path("archive"), m, {"status": "SUCCEEDED"})])
        page = render_html("example", "now", runs, charts, monitor_rows("example", runs), [], Path("report"))
        self.assertNotIn(malicious, page)
        self.assertIn("&lt;/script&gt;", page)
        self.assertNotIn("<script src=", page)
        data = page.split('<script id="chart-data" type="application/json">')[1].split("</script>")[0]
        self.assertEqual(json.loads(data)[0]["description"], malicious)
        self.assertIn("CRASHED", page)
        self.assertNotIn("完整数值", page)
        self.assertNotIn("absolute_error", page)
        self.assertNotIn("table-filter", page)

    def test_report_checks_selection_integrity_and_outputs_html(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = stored_fixture(root)
            self.assertEqual(archived_runs(root, "example")[0]["job_id"], "job-a")
            with self.assertRaises(ConfigurationError):
                report(root, "example", ["job-a", "missing"])
            self.assertFalse((root / "artifacts/example/reports").exists())
            with patch("report.static_figures", return_value=[]):
                result = report(root, "example", ["job-a"])
            self.assertEqual(Path(result["report"]).suffix, ".html")
            self.assertTrue(Path(result["report"]).is_file())
            summary = Path(result["report"]).with_name("summary.csv").read_text(encoding="utf-8-sig")
            self.assertIn("job_id", summary)
            self.assertIn("nan", summary)
            atomic_json(archive / "status.json", {"status": "CRASHED"})
            with self.assertRaises(PostprocessError):
                report(root, "example", ["job-a"])

    def test_report_reuses_deduplicated_selection_and_refuses_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stored_fixture(root)
            with patch("report.static_figures", return_value=[]):
                first = report(root, "example", ["job-a", "job-a"])
                second = report(root, "example", ["job-a"])
            self.assertEqual(first["report"], second["report"])
            self.assertFalse(first["reused"])
            self.assertTrue(second["reused"])
            self.assertEqual(first["runs"], 1)
            Path(first["report"]).write_text("corrupted", encoding="utf-8")
            with self.assertRaises(PostprocessError):
                report(root, "example", ["job-a"])

    def test_report_uses_csv_instead_of_manifest_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = stored_fixture(root)
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            manifest["monitors"]["u"] = [{"step": 99, "time": 99, "value": 123456}]
            manifest["comparisons"]["monitors"] = [{"monitor": "u", "reference_value": 999}]
            manifest["condition"]["references"] = {
                "reference-u": {"monitor": "u", "value": 1, "unit": "m/s", "reference_scale": {"value": 1, "unit": "m/s"}, "source": {"description": "analytic"}}
            }
            manifest["archive_integrity"]["manifest_content_sha256"] = manifest_digest(manifest)
            atomic_json(path / "manifest.json", manifest)
            before = (path / "manifest.json").read_bytes()
            with patch("report.static_figures", return_value=[]):
                result = report(root, "example")
            summary = json.loads(Path(result["report"]).with_name("summary.json").read_text(encoding="utf-8"))
            derived = summary["runs"][0]["manifest"]
            self.assertEqual(derived["monitors"]["u"][-1]["step"], 1)
            self.assertEqual(derived["comparisons"]["monitors"][0]["reference_value"], 1)
            self.assertEqual(derived["comparisons"]["monitors"][0]["status"], "UNAVAILABLE")
            self.assertEqual(derived["source_manifest"]["monitors"]["u"][0]["value"], 123456)
            self.assertIn("field_samples", derived)
            self.assertTrue(Path(result["report"]).with_name("monitors.csv").is_file())
            self.assertTrue(Path(result["report"]).with_name("field_errors.csv").is_file())
            self.assertEqual(before, (path / "manifest.json").read_bytes())

    def test_terminal_failure_report_has_redacted_logs_without_fake_curves(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "runs/job-a"
            (path / "logs").mkdir(parents=True)
            manifest = fixture()
            manifest["case"]["id"] = "example"
            atomic_json(path / "manifest.json", manifest)
            atomic_json(path / "status.json", {"status": "CRASHED", "diagnostics": ["token=private-value"]})
            (path / "logs/solver.log").write_text("api_key=private-value\nfailure details", encoding="utf-8")
            with patch("report.static_figures", return_value=[]):
                result = report(root, "example", ["job-a"])
            page = Path(result["report"]).read_text(encoding="utf-8")
            self.assertIn("CRASHED", page)
            self.assertIn("failure details", page)
            self.assertNotIn("private-value", page)
            data = page.split('<script id="chart-data" type="application/json">')[1].split("</script>")[0]
            self.assertEqual(json.loads(data), [])
            atomic_json(path / "status.json", {"status": "QUEUED"})
            with self.assertRaises(ConfigurationError):
                report(root, "example", ["job-a"])
            with self.assertRaises(ConfigurationError):
                report(root, "example")

    def test_report_selection_order_does_not_change_report_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stored_fixture(root, "job-a")
            stored_fixture(root, "job-b")
            with patch("report.static_figures", return_value=[]):
                first = report(root, "example", ["job-a", "job-b"])
                second = report(root, "example", ["job-b", "job-a", "job-b"])
            self.assertEqual(first["report"], second["report"])
            self.assertTrue(second["reused"])
            self.assertEqual(len(Path(first["report"]).parent.name), 64)

    def test_concurrent_report_requests_publish_one_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stored_fixture(root)
            context = multiprocessing.get_context("fork")
            queue = context.Queue()
            workers = [context.Process(target=report_worker, args=(str(root), queue)) for _ in range(2)]
            try:
                for worker in workers:
                    worker.start()
                results = [queue.get(timeout=15) for _ in workers]
                for worker in workers:
                    worker.join(timeout=15)
                    self.assertEqual(worker.exitcode, 0)
                self.assertFalse(any("error" in result for result in results), results)
                self.assertEqual(results[0]["report"], results[1]["report"])
                self.assertEqual(sum(result["reused"] for result in results), 1)
                reports = root / "artifacts/example/reports"
                self.assertEqual(len([path for path in reports.iterdir() if path.is_dir()]), 1)
            finally:
                for worker in workers:
                    if worker.is_alive():
                        worker.terminate()
                        worker.join()
                queue.close()

    def test_list_runs_cli_and_repeated_job_ids(self):
        args = parser().parse_args(["list", "runs", "--case", "example"])
        self.assertEqual(args.case, "example")
        args = parser().parse_args(["report", "example", "--job-id", "job-a", "--job-id", "job-b"])
        self.assertEqual(args.job_id, ["job-a", "job-b"])


if __name__ == "__main__":
    unittest.main()
