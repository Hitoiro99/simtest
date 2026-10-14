"""Fixed native result regression: topology, coordinates, time switching, values."""
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PVPYTHON=Path("/opt/paraviewopenfoam510/bin/pvpython")


def native_values(path):
    text=path.read_text()
    match=re.search(r"internalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;",text,re.S)
    if not match: raise AssertionError("Fixture field shape changed")
    values=[[float(v) for v in row.split()] for row in re.findall(r"\(([^()]+)\)",match.group(2))]
    if len(values)!=int(match.group(1)): raise AssertionError("Fixture count mismatch")
    return values


@unittest.skipUnless(PVPYTHON.is_file(),"requires installed pvpython/VTK")
class ReaderRegression(unittest.TestCase):
    def test_native_all_times_and_serialized_minimal_arrays(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp); case=directory/"case"; shutil.copytree(ROOT/"tests"/"fixtures"/"openfoam12",case)
            time_raw=(case/"1"/"uniform"/"time").read_text()
            actual_time=float(re.search(r"(?m)^value\s+([^;]+);",time_raw).group(1))
            request={"mode":"native","case":str(case),"times":[{"name":"0","reader_time":0,"time":0},{"name":"1","reader_time":1,"time":actual_time}],
                     "fields":[{"canonical":"velocity","native":"U","factor":1,"unit":"m/s","domain":"internalMesh","components":3}],
                     "output":str(directory/"normalized"),"response":str(directory/"response.json")}
            file=directory/"request.json"; file.write_text(json.dumps(request))
            subprocess.run([str(PVPYTHON),"--force-offscreen-rendering",str(ROOT/"simtest"/"vtk_bridge.py"),str(file)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
            datasets=json.loads((directory/"response.json").read_text())["datasets"]
            self.assertEqual(len(datasets),2)
            self.assertEqual([d["time"] for d in datasets],[0,actual_time])
            for dataset,label in zip(datasets,("0","1")):
                values=native_values(case/label/"U")
                self.assertEqual(dataset["cells"],128); self.assertEqual(dataset["points"],330)
                self.assertEqual(set(dataset["arrays"]),{"velocity","velocity_x","velocity_y","velocity_z","velocity_magnitude","cell_volume","original_cell_id"})
                for sample,target in zip(dataset["samples"],values):
                    self.assertGreater(sample["volume"],0)
                    self.assertTrue(0<=sample["center"][1]<=.1)
                    for value,expected in zip(sample["value"],target):
                        # The bundled reader stores Float32 arrays. This is a
                        # decoder fidelity bound, not a numerical acceptance threshold.
                        self.assertTrue(math.isclose(value,expected,rel_tol=2e-7,abs_tol=1e-12),(value,expected))
            self.assertLess(datasets[1]["samples"][64]["value"][0],datasets[0]["samples"][64]["value"][0])

