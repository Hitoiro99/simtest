"""Faithful OpenFOAM function-object and log readers."""
import csv
import math
import re

from solvers.exceptions import MissingOutputError, MonitorParseError
from solvers.models import MonitorRecord
from solvers.registry import mapped
from simtest.units import factor

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[+-]?(?:nan|inf)"


def log_axis(path):
    text = path.read_text(encoding="utf-8",errors="replace")
    current = None; axis = []; residuals = {}; warnings = []
    for line_no,line in enumerate(text.splitlines(),1):
        match = re.match(r"^Time = (\S+)\s*$",line)
        if match:
            token = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(s|ms)?",match.group(1))
            if not token: raise MonitorParseError("未知日志时间单位/格式")
            try: time_value = float(token.group(1))*(.001 if token.group(2)=="ms" else 1)
            except ValueError: raise MonitorParseError("非法原生物理时间")
            if not math.isfinite(time_value): raise MonitorParseError("非有限物理时间")
            if axis and time_value <= axis[-1]: raise MonitorParseError("原生时间轴重复或倒序")
            axis.append(time_value); current = (len(axis),time_value)
        match = re.search(r"Solving for (\w+), Initial residual = (\S+),",line)
        if match and current:
            try: value = float(match.group(2))
            except ValueError:
                warnings.append({"kind":"bad_line","file":str(path),"line":line_no}); continue
            name = "residual:"+match.group(1)
            # One initial residual per equation/time step, first linear solve.
            residuals.setdefault(name,{}).setdefault(current,value)
    if not axis: raise MissingOutputError("日志中没有迭代/时间记录")
    return axis,residuals,warnings


def function_tables(work):
    tables = {}; warnings = []
    for file in sorted((work/"postProcessing").rglob("*.dat")):
        header = None
        for number,line in enumerate(file.read_text(encoding="utf-8",errors="replace").splitlines(),1):
            if not line.strip(): continue
            if line.lstrip().startswith("#"):
                candidate = line.lstrip("# \t").split()
                if candidate and candidate[0] == "Time": header = candidate
                continue
            if header is None:
                raise MonitorParseError("数据行之前缺少 Time 表头: " + str(file))
            tokens = re.findall(r"\([^)]*\)|\S+", line)
            if len(tokens) != len(header):
                warnings.append({"kind":"bad_line","file":str(file),"line":number,"reason":"列数与表头不一致"})
            try:
                time_value = float(tokens[0])
                if not math.isfinite(time_value): raise ValueError("nonfinite time")
            except (ValueError,IndexError):
                # Without an axis, the record cannot be placed. Fail explicitly
                # instead of making an earlier valid record look like the last.
                raise MonitorParseError("监控记录的时间不可解析: %s:%s" % (file,number))
            parsed = []
            for index,name in enumerate(header[1:],1):
                token = tokens[index] if index<len(tokens) else "nan"
                try: values = [float(v) for v in token.strip("()").split()]
                except ValueError:
                    values = [float("nan")]
                    warnings.append({"kind":"invalid","native_monitor":name,"time":time_value,"file":str(file),"line":number,"reason":"不可解析的监控值"})
                if len(values) == 1: parsed.append((name,values[0]))
                elif len(values) == 3: parsed.extend((name+"."+c,v) for c,v in zip("xyz",values))
                else: raise MonitorParseError("监控列结构未知: " + name)
            for name,value in parsed:
                values = tables.setdefault(name,{})
                if time_value in values: raise MonitorParseError("重复监控记录/多个冲突来源: " + name)
                values[time_value] = value
    return tables,warnings


def normalize_monitors(context,adapter):
    axis,residuals,warnings = log_axis(context.run_dir/"logs"/"solver.log")
    tables,table_warnings = function_tables(context.work); warnings += table_warnings
    step_by_time = {value:index+1 for index,value in enumerate(axis)}
    start = float(adapter.dictionary(context,context.input/"system"/"controlDict","startTime").strip().rstrip(";"))
    step_by_time[start] = 0
    records = {}
    for name,declaration in context.case.get("monitors",{}).items():
        native,unit = mapped(declaration,name,adapter)
        conversion = factor(unit,declaration.get("unit",""))
        data = []
        if native.startswith("residual:"):
            if native not in residuals: raise MissingOutputError("缺少必需残差: " + native)
            pairs = [(step,time,value) for (step,time),value in residuals[native].items()]
        else:
            if native not in tables: raise MissingOutputError("缺少必需 function-object 监控: " + native)
            pairs = []
            for time,value in tables[native].items():
                if time not in step_by_time: raise MonitorParseError("监控时间未能与求解器原生时间轴对应: " + str(time))
                pairs.append((step_by_time[time],time,value))
        for step,time,value in sorted(pairs):
            value *= conversion
            quality = "valid" if math.isfinite(value) else "invalid"
            data.append(MonitorRecord(name,step,time,value,declaration.get("unit",""),quality))
            if quality == "invalid": warnings.append({"kind":"invalid","monitor":name,"step":step,"time":time,"reason":"NaN/Inf"})
        if not data: raise MissingOutputError("必需监控没有记录: " + name)
        records[name] = data
    if not records: raise MissingOutputError("案例未登记任何可读取监控项")
    aligned = {}
    for name,data in records.items():
        for record in data: aligned.setdefault((record.step,record.time),{})[name] = record.value
    context.normalized.mkdir(parents=True,exist_ok=True)
    with (context.normalized/"monitors.csv").open("w",newline="",encoding="utf-8") as stream:
        writer = csv.writer(stream); writer.writerow(["step","time"]+list(records))
        for (step,time),row in sorted(aligned.items()): writer.writerow([step,time]+[row.get(name,"") for name in records])
    context.manifest["monitor_mapping"] = {name:{"native":mapped(declaration,name,adapter)[0],"unit":declaration.get("unit",""),
                "kind":"residual" if mapped(declaration,name,adapter)[0].startswith("residual:") else "monitor"} for name,declaration in context.case.get("monitors",{}).items()}
    context.manifest["solver_time_axis"] = {"start":start,"steps":axis}
    return records,warnings
