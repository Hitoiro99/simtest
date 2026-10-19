"""标准回读、不可变发布及工作区清理的边界回归。"""

import copy
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from archive import archive, archive_path, cleanup_run, load_observations, manifest_digest, verify_archive
from common.io import atomic_json, inventory
from solvers.exceptions import PostprocessError


def make_context(root, fields=False):
    root = Path(root)
    run = root / "runs" / ("a" * 64)
    for name in ("work", "input", "logs", "normalized"):
        (run / name).mkdir(parents=True)
    (run / "work" / "native-result").write_text("retain until validation")
    (run / "input" / "input.txt").write_text("fixed input")
    (run / "logs" / "solver.log").write_text("solver completed")
    (run / "normalized" / "monitors.csv").write_text("step,time,u,v\n0,0,1,\n1,1,nan,2\n2,2,inf,3\n")
    case = {"id": "case", "monitors": {"u": {"unit": "m/s"}, "v": {"unit": "m/s"}}}
    condition = {"references": {}}
    manifest = {
        "job_id": run.name, "identity": {"case": "case", "condition": "default"},
        "case": case, "condition": condition, "actual_solver": {"name": "OpenFOAM", "version": "12"},
        "execution": {"processes": 1}, "input_sha256": inventory(run / "input"), "fields": [],
        "monitors": {"u": [{"step": 999, "time": 999, "value": 999}]},
    }
    if fields:
        case["fields"] = {"velocity": {"unit": "m/s"}}
        condition["references"] = {
            "r": {"field": "velocity", "domain": "fluid", "expression": {"x": "0", "y": "0", "z": "0"}}
        }
        directory = run / "normalized" / "fields"
        directory.mkdir()
        manifest["fields"] = [write_vtu(directory / "velocity-0.vtu")]
        manifest["field_reader"] = {"times": [{"time": 0}]}
    context = SimpleNamespace(
        root=root, run_dir=run, work=run / "work", input=run / "input", normalized=run / "normalized",
        case=case, condition=condition, condition_id="default", info=SimpleNamespace(name="OpenFOAM", version="12"),
        manifest=manifest,
    )
    atomic_json(run / "manifest.json", manifest)
    return context


def write_vtu(file):
    tree = ET.Element("VTKFile", type="UnstructuredGrid")
    grid = ET.SubElement(tree, "UnstructuredGrid")
    metadata = ET.SubElement(grid, "FieldData")

    def numeric(parent, name, values, components=1, kind="Float64"):
        attrs = {"Name": name, "format": "ascii", "type": kind}
        if components != 1:
            attrs["NumberOfComponents"] = str(components)
        array = ET.SubElement(parent, "DataArray", attrs)
        array.text = " ".join(str(value) for value in values)
        return array

    numeric(metadata, "physical_time", [0])
    for name, value in (("domain", "fluid"), ("unit", "m/s"), ("coordinate_unit", "m"), ("time_unit", "s")):
        array = ET.SubElement(metadata, "Array", Name=name, type="String", format="ascii", NumberOfTuples="1")
        array.text = " ".join(str(byte) for byte in list(value.encode("utf-8")) + [0])
    piece = ET.SubElement(grid, "Piece", NumberOfCells="1", NumberOfPoints="4")
    ET.SubElement(piece, "PointData")
    data = ET.SubElement(piece, "CellData")
    numeric(data, "velocity", [3, 4, 0], 3)
    for name, values in (("velocity_x", [3]), ("velocity_y", [4]), ("velocity_z", [0]),
                         ("velocity_magnitude", [5]), ("cell_volume", [1 / 6])):
        numeric(data, name, values)
    numeric(data, "cell_center", [0.25, 0.25, 0.25], 3)
    numeric(data, "original_cell_id", [7], kind="Int64")
    points = ET.SubElement(piece, "Points")
    numeric(points, "Points", [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1], 3)
    cells = ET.SubElement(piece, "Cells")
    numeric(cells, "connectivity", [0, 1, 2, 3], kind="Int64")
    numeric(cells, "offsets", [4], kind="Int64")
    numeric(cells, "types", [10], kind="UInt8")
    ET.ElementTree(tree).write(file, encoding="utf-8", xml_declaration=True)
    return {
        "field": "velocity", "domain": "fluid", "time": 0, "unit": "m/s", "file": str(file),
        "cells": 1, "points": 4, "arrays": [array.get("Name") for array in data],
        "samples": [{"cell_id": 999, "center": [999, 999, 999], "volume": 999, "value": [999, 999, 999]}],
    }


class ArchiveTests(unittest.TestCase):
    def test_monitor_read_preserves_invalid_sampling_and_ignores_manifest_values(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp)
            monitors = load_observations(context.run_dir, context.manifest)["monitors"]
            self.assertEqual([row["step"] for row in monitors["u"]], [0, 1, 2])
            self.assertEqual([row["step"] for row in monitors["v"]], [1, 2])
            self.assertTrue(math.isnan(monitors["u"][1]["value"]))
            self.assertEqual(monitors["u"][1]["quality"], "invalid")
            self.assertEqual(monitors["u"][0]["unit"], "m/s")

    def test_duplicate_backward_or_missing_monitor_records_are_rejected(self):
        samples = ["0,0,1,2\n0,0,2,3\n", "1,1,1,2\n0,0,2,3\n", "0,0,1,\n", "0,nan,1,2\n", "0,0,1,2,3\n"]
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp)
            for rows in samples:
                with self.subTest(rows=rows):
                    (context.normalized / "monitors.csv").write_text("step,time,u,v\n" + rows)
                    with self.assertRaises(PostprocessError):
                        load_observations(context.run_dir, context.manifest)

    def test_field_read_uses_serialized_geometry_and_values(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp, fields=True)
            sample = load_observations(context.run_dir, context.manifest)["fields"][0]["samples"][0]
            self.assertEqual(sample["cell_id"], 7)
            self.assertEqual(sample["center"], [0.25, 0.25, 0.25])
            self.assertEqual(sample["value"], [3, 4, 0])
            self.assertAlmostEqual(sample["volume"], 1 / 6)

    def test_field_topology_geometry_components_units_and_times_are_checked(self):
        mutations = [("connectivity", "0 1 2 99"), ("offsets", "3"), ("cell_volume", "0"),
                     ("cell_center", "nan 0 0"), ("velocity_y", "100"), ("velocity_magnitude", "100"),
                     ("physical_time", "1"), ("unit", "80 97 0")]
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp, fields=True)
            file = Path(context.manifest["fields"][0]["file"])
            original = file.read_bytes()
            for name, text in mutations:
                with self.subTest(name=name):
                    file.write_bytes(original)
                    tree = ET.parse(file)
                    tree.find(".//*[@Name='" + name + "']").text = text
                    tree.write(file, encoding="utf-8", xml_declaration=True)
                    with self.assertRaises(PostprocessError):
                        load_observations(context.run_dir, context.manifest)

    def test_all_output_times_and_no_extra_fields_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp, fields=True)
            context.manifest["field_reader"]["times"].append({"time": 1})
            with self.assertRaisesRegex(PostprocessError, "全部实际输出时刻"):
                load_observations(context.run_dir, context.manifest)
            context.manifest["field_reader"]["times"].pop()
            (context.normalized / "fields" / "extra.vtu").write_text("extra")
            with self.assertRaises(PostprocessError):
                load_observations(context.run_dir, context.manifest)

    def test_pvd_references_are_checked_and_single_time_index_is_optional(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp, fields=True)
            pvd = context.normalized / "fields" / "fields.pvd"
            pvd.write_text('<VTKFile type="Collection"><Collection><DataSet group="velocity" timestep="0" file="../bad.vtu"/></Collection></VTKFile>')
            with self.assertRaises(PostprocessError):
                load_observations(context.run_dir, context.manifest)
            pvd.unlink()
            self.assertEqual(len(load_observations(context.run_dir, context.manifest)["fields"]), 1)

    def test_no_field_reference_must_not_create_fields_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp)
            (context.normalized / "fields").mkdir()
            with self.assertRaises(PostprocessError):
                load_observations(context.run_dir, context.manifest)

    def test_archive_is_independent_immutable_and_cleanup_removes_whole_run(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp, fields=True)
            final = archive(context, {"status": "SUCCEEDED", "history": []})
            self.assertEqual(final, archive_path(context))
            self.assertTrue(context.work.exists())
            saved = json.loads((final / "manifest.json").read_text())
            self.assertEqual(saved["fields"][0]["file"], "normalized/fields/velocity-0.vtu")
            before = inventory(final)
            cleanup_run(context, final)
            self.assertFalse(context.run_dir.exists())
            self.assertEqual(inventory(final), before)
            self.assertTrue(verify_archive(final))
            sample = load_observations(final, saved)["fields"][0]["samples"][0]
            self.assertEqual(sample["value"], [3, 4, 0])
            cleanup_run(context, final)

    def test_only_success_is_archived_and_existing_archive_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp)
            with self.assertRaises(PostprocessError):
                archive(context, {"status": "CRASHED"})
            self.assertFalse(archive_path(context).exists())
            final = archive(context, {"status": "SUCCEEDED"})
            before = inventory(final)
            with self.assertRaises(PostprocessError):
                archive(context, {"status": "SUCCEEDED"})
            self.assertEqual(inventory(final), before)

    def test_hash_valid_but_unreadable_result_prevents_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp)
            final = archive(context, {"status": "SUCCEEDED"})
            (final / "normalized" / "monitors.csv").write_text("broken")
            manifest = json.loads((final / "manifest.json").read_text())
            hashes = inventory(final)
            hashes.pop("manifest.json")
            manifest["archive_integrity"] = {"files": hashes, "manifest_content_sha256": manifest_digest(manifest)}
            atomic_json(final / "manifest.json", manifest)
            with self.assertRaises(PostprocessError):
                cleanup_run(context, final)
            self.assertTrue(context.work.exists())

    def test_failed_staging_validation_retains_raw_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp)
            with patch("archive.verify_archive", side_effect=PostprocessError("broken copied data")):
                with self.assertRaises(PostprocessError):
                    archive(context, {"status": "SUCCEEDED"})
            self.assertTrue((context.work / "native-result").exists())
            self.assertFalse(archive_path(context).exists())

    def test_modified_input_prevents_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp)
            (context.input / "input.txt").write_text("modified")
            with self.assertRaises(PostprocessError):
                archive(context, {"status": "SUCCEEDED"})
            self.assertTrue(context.work.exists())

    def test_cleanup_refuses_wrong_identity_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            context = make_context(temp)
            final = archive(context, {"status": "SUCCEEDED"})
            saved = copy.deepcopy(context.manifest["identity"])
            context.manifest["identity"]["condition"] = "other"
            with self.assertRaises(PostprocessError):
                cleanup_run(context, final)
            context.manifest["identity"] = saved
            link = context.work / "link"
            link.symlink_to(context.input, target_is_directory=True)
            with self.assertRaises(Exception):
                cleanup_run(context, final)
            self.assertTrue(context.work.exists())


if __name__ == "__main__":
    unittest.main()
