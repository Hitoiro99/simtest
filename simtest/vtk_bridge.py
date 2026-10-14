"""Run using pvpython; pure stdlib + bundled VTK, no numpy dependency."""
import json
import math
import sys
from pathlib import Path

import vtk


def grids(block, prefix=""):
    if isinstance(block,vtk.vtkUnstructuredGrid):
        yield prefix,block
    elif isinstance(block,vtk.vtkMultiBlockDataSet):
        for index in range(block.GetNumberOfBlocks()):
            child = block.GetBlock(index)
            if child is None: continue
            metadata = block.GetMetaData(index)
            name = metadata.Get(vtk.vtkCompositeDataSet.NAME()) if metadata and metadata.Has(vtk.vtkCompositeDataSet.NAME()) else str(index)
            for result in grids(child, prefix+"/"+name if prefix else name): yield result


def geometry(grid):
    centres = vtk.vtkCellCenters(); centres.SetInputData(grid); centres.Update()
    sizes = vtk.vtkCellSizeFilter(); sizes.SetInputData(grid)
    sizes.SetComputeLength(False); sizes.SetComputeArea(False); sizes.SetComputeVolume(True); sizes.Update()
    volumes = sizes.GetOutput().GetCellData().GetArray("Volume")
    if volumes is None: raise ValueError("Cannot obtain cell volumes")
    result = []
    native_ids = grid.GetCellData().GetArray("cellID")
    for i in range(grid.GetNumberOfCells()):
        center = centres.GetOutput().GetPoint(i)
        volume = volumes.GetValue(i)
        if volume <= 0 or not math.isfinite(volume): raise ValueError("Invalid cell volume")
        result.append((list(center),volume,int(native_ids.GetTuple1(i)) if native_ids else i))
    return result


def scalar_array(name, values):
    array = vtk.vtkDoubleArray(); array.SetName(name)
    for value in values: array.InsertNextValue(value)
    return array


def export(grid, spec, time, output, domain):
    data = grid.GetCellData().GetArray(spec["native"])
    if data is None: raise ValueError("Missing field " + spec["native"])
    if data.GetNumberOfTuples() != grid.GetNumberOfCells(): raise ValueError("Field/mesh counts differ")
    components = data.GetNumberOfComponents()
    if components not in (1,3): raise ValueError("Unsupported field component count")
    if components != spec["components"]: raise ValueError("Native vector/expression structure mismatch")
    geo = geometry(grid)
    values = [[value*spec["factor"] for value in data.GetTuple(i)] for i in range(grid.GetNumberOfCells())]
    clean = vtk.vtkUnstructuredGrid(); clean.CopyStructure(grid)
    array = vtk.vtkDoubleArray(); array.SetName(spec["canonical"]); array.SetNumberOfComponents(components)
    for row in values: array.InsertNextTuple(row)
    clean.GetCellData().AddArray(array)
    if components == 3:
        for index,c in enumerate("xyz"): clean.GetCellData().AddArray(scalar_array(spec["canonical"]+"_"+c,[row[index] for row in values]))
        clean.GetCellData().AddArray(scalar_array(spec["canonical"]+"_magnitude",[math.sqrt(sum(v*v for v in row)) for row in values]))
    clean.GetCellData().AddArray(scalar_array("cell_volume",[g[1] for g in geo]))
    ids = vtk.vtkIdTypeArray(); ids.SetName("original_cell_id")
    for g in geo: ids.InsertNextValue(g[2])
    clean.GetCellData().AddArray(ids)
    clean.GetFieldData().AddArray(scalar_array("physical_time",[time]))
    for name,value in (("domain",domain),("unit",spec["unit"]),("coordinate_unit","m"),("time_unit","s")):
        strings = vtk.vtkStringArray(); strings.SetName(name); strings.InsertNextValue(value); clean.GetFieldData().AddArray(strings)
    file = output/(spec["canonical"]+"-"+format(time,".12g")+".vtu")
    writer = vtk.vtkXMLUnstructuredGridWriter(); writer.SetFileName(str(file)); writer.SetInputData(clean); writer.SetDataModeToAscii()
    if writer.Write() != 1: raise ValueError("VTU write failed")
    # Verify the serialized result, not just the writer return value.
    reader = vtk.vtkXMLUnstructuredGridReader(); reader.SetFileName(str(file)); reader.Update()
    restored = reader.GetOutput()
    expected = {clean.GetCellData().GetArrayName(i) for i in range(clean.GetCellData().GetNumberOfArrays())}
    actual = {restored.GetCellData().GetArrayName(i) for i in range(restored.GetCellData().GetNumberOfArrays())}
    if restored.GetNumberOfCells()!=grid.GetNumberOfCells() or restored.GetNumberOfPoints()!=grid.GetNumberOfPoints() or actual!=expected:
        raise ValueError("VTU roundtrip validation failed")
    return {"time":time,"domain":domain,"field":spec["canonical"],"unit":spec["unit"],"file":str(file),
            "cells":grid.GetNumberOfCells(),"points":grid.GetNumberOfPoints(),"arrays":sorted(actual),
            "samples":[{"cell_id":g[2],"center":g[0],"volume":g[1],"value":v} for g,v in zip(geo,values)]}


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    output = Path(request["output"]); output.mkdir(parents=True,exist_ok=True)
    datasets = []
    if request["mode"] == "native":
        marker = Path(request["case"])/"result.foam"; marker.touch()
        reader = vtk.vtkOpenFOAMReader(); reader.SetFileName(str(marker))
        reader.SetCreateCellToPoint(False); reader.SetSkipZeroTime(False); reader.SetDecomposePolyhedra(False)
        reader.UpdateInformation()
        times = reader.GetTimeValues()
        available = [times.GetValue(i) for i in range(times.GetNumberOfTuples())]
        expected = [entry["reader_time"] for entry in request["times"]]
        if set(available)!=set(expected): raise ValueError("Reader/native metadata time set differs: %s vs %s" % (available,expected))
        reader.DisableAllCellArrays()
        for spec in request["fields"]: reader.SetCellArrayStatus(spec["native"],1)
        for entry in request["times"]:
            # SetTimeValue alone does not invalidate vtkAlgorithm's cached
            # output on the bundled VTK 9.0 build. Request the pipeline time.
            reader.UpdateTimeStep(entry["reader_time"])
            candidates = list(grids(reader.GetOutput()))
            for spec in request["fields"]:
                matching = [(name,grid) for name,grid in candidates if name == spec["domain"]]
                if len(matching)!=1: raise ValueError("Domain must match exactly once: %s; found %s" % (spec["domain"],[n for n,g in candidates]))
                datasets.append(export(matching[0][1],spec,entry["time"],output,spec["domain"]))
    elif request["mode"] == "exchange":
        for entry in request["times"]:
            file = Path(request["case"])/"VTK"/(Path(request["case"]).name+"_"+entry["name"]+".vtk")
            if not file.is_file(): raise ValueError("Missing native export " + str(file))
            reader = vtk.vtkUnstructuredGridReader(); reader.SetFileName(str(file)); reader.ReadAllScalarsOn(); reader.ReadAllVectorsOn(); reader.Update()
            grid = reader.GetOutput()
            if grid.GetNumberOfCells()==0: raise ValueError("Empty exchange mesh")
            for spec in request["fields"]:
                if spec["domain"]!="internalMesh": raise ValueError("Exchange fallback does not support undeclared region layouts")
                datasets.append(export(grid,spec,entry["time"],output,spec["domain"]))
    else: raise ValueError("Unknown reader mode")
    # Non-finite field values remain invalid, encoded without non-standard JSON.
    def safe(value):
        if isinstance(value,float) and not math.isfinite(value): return str(value)
        if isinstance(value,list): return [safe(x) for x in value]
        if isinstance(value,dict): return {k:safe(v) for k,v in value.items()}
        return value
    Path(request["response"]).write_text(json.dumps(safe({"vtk_version":vtk.vtkVersion.GetVTKVersion(),"datasets":datasets}),allow_nan=False))


if __name__ == "__main__": main()
