import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from simtest.archive import manifest_digest
from simtest.cli import parser
from simtest.io import atomic_json, inventory
from simtest.report import archived_runs, report
from simtest.report_html import build_charts, monitor_rows, render_html
from solvers.exceptions import ConfigurationError, PostprocessError


def fixture():
    return {"job_id": "job-a", "created": "2026-10-13", "identity": {"condition": "default"},
            "actual_solver": {"name": "OpenFOAM", "version": "12"},
            "execution": {"backend": "serial", "processes": 1},
            "case": {"monitors": {"u": {"unit": "m/s"}}}, "condition": {},
            "monitors": {"u": [{"step": 0, "time": 0, "value": 1},
                                {"step": 1, "time": 1, "value": "nan", "quality": "invalid"}]},
            "comparisons": {"monitors": [], "fields": []}}


class ReportTests(unittest.TestCase):
    def test_invalid_last_and_sampling_axes_are_preserved(self):
        m = fixture()
        m["monitors"]["u"].append({"step": 2, "time": None, "value": "inf"})
        runs = [(Path("archive"), m, {"status": "SUCCEEDED"})]
        charts = build_charts(runs)
        self.assertEqual(len(charts), 2)
        self.assertEqual(charts[0]["series"][0]["points"][1]["y"], None)
        self.assertEqual(charts[0]["series"][0]["points"][1]["raw"], "nan")
        self.assertEqual(charts[1]["xlabel"], "Step")
        self.assertEqual(monitor_rows("example", runs)[0]["last_value"], "inf")

    def test_field_comparisons_are_grouped_without_bridging_unavailable(self):
        m = fixture()
        row = {"field": "velocity", "domain": "fluid", "reference_id": "r", "component": "x",
               "time": 0, "unit": "m/s", "status": "AVAILABLE",
               "absolute_error": {"max": .2, "mean": .1, "rms": .15},
               "normalized_error": {"max": .02, "mean": .01, "rms": .015}}
        m["comparisons"]["fields"] = [row, dict(row, time=1, status="UNAVAILABLE", reason="bad field"),
            dict(row, time=2), dict(row, domain="solid"), dict(row, field="other"), dict(row, reference_id="r2")]
        fields = [c for c in build_charts([(Path("archive"), m, {"status": "SUCCEEDED"})]) if c["kind"] == "field"]
        self.assertEqual(len(fields), 4)
        points = fields[0]["series"][0]["points"]
        self.assertEqual([p["y"] for p in points], [2, None, 2])
        self.assertEqual(points[0]["metrics"]["absolute_error.mean"], .1)

    def test_html_is_offline_and_escapes_archived_text(self):
        m = fixture()
        malicious = '</script><script>alert("injected")</script>'
        m["case"]["monitors"]["u"]["display_name"] = malicious
        status = {"status": "CRASHED", "diagnostics": [malicious]}
        runs = [(Path("archive"), m, status)]
        charts = build_charts(runs)
        page = render_html("example", "now", runs, charts, monitor_rows("example", runs), [], Path("report"))
        self.assertNotIn(malicious, page)
        self.assertIn("&lt;/script&gt;", page)
        self.assertNotIn('<script src=', page)
        data = page.split('<script id="chart-data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(data)[0]["description"], malicious)
        self.assertIn("CRASHED", page)

    def test_report_checks_selection_integrity_and_outputs_html(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "artifacts/example/runs/default/OpenFOAM/12/job-a"
            archive.mkdir(parents=True)
            atomic_json(archive / "status.json", {"status": "SUCCEEDED"})
            m = fixture()
            m["archive_integrity"] = {"files": inventory(archive), "manifest_content_sha256": manifest_digest(m)}
            atomic_json(archive / "manifest.json", m)
            self.assertEqual(archived_runs(root, "example")[0]["job_id"], "job-a")
            with self.assertRaises(ConfigurationError): report(root, "example", ["job-a", "missing"])
            self.assertFalse((root / "artifacts/example/reports").exists())
            with patch("simtest.report.static_figures", return_value=[]):
                result = report(root, "example", ["job-a"])
            self.assertEqual(Path(result["report"]).suffix, ".html")
            self.assertTrue(Path(result["report"]).is_file())
            summary = Path(result["report"]).with_name("summary.csv").read_text(encoding="utf-8-sig")
            self.assertIn("job_id", summary)
            self.assertIn("nan", summary)
            atomic_json(archive / "status.json", {"status": "CRASHED"})
            with self.assertRaises(PostprocessError): report(root, "example", ["job-a"])

    def test_list_runs_cli_and_repeated_job_ids(self):
        args = parser().parse_args(["list", "runs", "--case", "example"])
        self.assertEqual(args.case, "example")
        args = parser().parse_args(["report", "example", "--job-id", "job-a", "--job-id", "job-b"])
        self.assertEqual(args.job_id, ["job-a", "job-b"])


if __name__ == "__main__":
    unittest.main()
