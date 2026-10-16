from __future__ import annotations

from abc import ABC, abstractmethod
import datetime
import json
import math
import os
import queue
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

from .exceptions import CancelledError, ConfigurationError, SolverCrashError, SolverTimeoutError
from .models import StageResult


def redact(text):
    return re.sub(r"(?i)\b(password|token|secret|license_key|api_key)\s*[:=]\s*([^\s,;]+)", r"\1=[REDACTED]", text)


def terminate_group(pid):
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def supervise(command, log, heartbeat=None):
    """One process group per command; wait4 obtains per-command resource usage."""
    if os.name != "posix":
        raise ConfigurationError("执行器必须在 Linux/WSL 内运行")
    if not command.argv or not all(isinstance(v, str) and "\x00" not in v for v in command.argv):
        raise ConfigurationError("非法命令参数数组")
    start = time.monotonic()
    last_output = start
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    output = queue.Queue()
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        command.argv,
        cwd=str(command.cwd),
        env=command.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    def collect():
        for line in iter(process.stdout.readline, b""):
            output.put(line)
        process.stdout.close()

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    exitcode = None
    reason = None
    usage = None
    peak_rss = 0
    try:
        with Path(log).open("w", encoding="utf-8") as stream:
            while exitcode is None:
                while True:
                    try:
                        line = output.get_nowait()
                    except queue.Empty:
                        break
                    stream.write(redact(line.decode("utf-8", errors="replace")))
                    stream.flush()
                    last_output = time.monotonic()
                now = time.monotonic()
                if heartbeat:
                    heartbeat(now - start, now - last_output)
                # Aggregate resident memory of the process group, without external dependencies.
                resident = 0
                for item in Path("/proc").iterdir():
                    if not item.name.isdigit():
                        continue
                    try:
                        stat = (item / "stat").read_text().split(") ", 1)[1].split()
                        if int(stat[2]) == process.pid:
                            resident += int(stat[21]) * os.sysconf("SC_PAGE_SIZE")
                    except (OSError, ValueError, IndexError):
                        pass
                peak_rss = max(peak_rss, resident)
                pid, status, resource = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    usage = resource
                    if os.WIFSIGNALED(status):
                        exitcode = -os.WTERMSIG(status)
                    else:
                        exitcode = os.WEXITSTATUS(status)
                    process.returncode = exitcode
                    break
                if now - start > command.timeout:
                    reason = "墙钟超时"
                elif command.heartbeat_timeout and now - last_output > command.heartbeat_timeout:
                    reason = "无日志心跳超时"
                if reason:
                    terminate_group(process.pid)
                    _, status, usage = os.wait4(process.pid, 0)
                    if os.WIFSIGNALED(status):
                        exitcode = -os.WTERMSIG(status)
                    else:
                        exitcode = os.WEXITSTATUS(status)
                    process.returncode = exitcode
                    break
                time.sleep(0.05)
            reader.join(timeout=3)
            while not output.empty():
                stream.write(redact(output.get().decode("utf-8", errors="replace")))
    except KeyboardInterrupt:
        terminate_group(process.pid)
        try:
            _, status, usage = os.wait4(process.pid, 0)
            process.returncode = -signal.SIGINT
        except ChildProcessError:
            pass
        reader.join(timeout=3)
        raise CancelledError("用户取消，求解器进程组已终止", stage="execute", log=str(log))
    except BaseException:
        terminate_group(process.pid)
        try:
            os.wait4(process.pid, 0)
            process.returncode = -signal.SIGTERM
        except ChildProcessError:
            pass
        raise
    # A launcher can exit while descendants survive; never leave the command group running.
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        pass
    else:
        terminate_group(process.pid)
    diagnostics = {
        "argv": command.argv,
        "cwd": str(command.cwd),
        "exit_code": exitcode,
        "start": started,
        "end": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "wall_seconds": time.monotonic() - start,
    }
    if usage:
        diagnostics["cpu_seconds"] = usage.ru_utime + usage.ru_stime
        diagnostics["peak_memory_bytes"] = max(peak_rss, int(usage.ru_maxrss) * 1024)
    else:
        diagnostics["cpu_seconds"] = None
        diagnostics["peak_memory_bytes"] = max(peak_rss, 0)
    diagnostics.update({"memory_method": "sampled process-group RSS + wait4 ru_maxrss", "log": str(log)})
    if reason:
        raise SolverTimeoutError(reason, stage="execute", **diagnostics)
    if exitcode:
        raise SolverCrashError("命令异常退出: %s" % exitcode, stage="execute", **diagnostics)
    return StageResult(elapsed=diagnostics["wall_seconds"], diagnostics=diagnostics)


class SolverAdapter(ABC):
    def template_filters(self):
        return {
            "real": self.format_real,
            "integer": self.format_integer,
            "boolean": self.format_boolean,
            "string": self.format_string,
            "path": self.format_path,
        }

    def format_real(self, value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ConfigurationError("real 拒绝 NaN/Inf/布尔值")
        result = format(value, ".17g")
        if "." in result or "e" in result.lower():
            return result
        return result + ".0"

    def format_integer(self, value):
        if type(value) is not int:
            raise ConfigurationError("integer 必须是整数，不能截断")
        return str(value)

    def format_boolean(self, value):
        if type(value) is not bool:
            raise ConfigurationError("boolean 必须是布尔值")
        return "true" if value else "false"

    def format_string(self, value):
        if not isinstance(value, str) or "\x00" in value:
            raise ConfigurationError("非法字符串")
        return json.dumps(value, ensure_ascii=False)

    def format_path(self, value):
        if not isinstance(value, (str, Path)):
            raise ConfigurationError("path 必须为路径字符串")
        return self.format_string(str(value))

    @abstractmethod
    def probe(self, context):
        pass

    @abstractmethod
    def validate(self, context):
        pass

    @abstractmethod
    def preprocess(self, context):
        pass

    @abstractmethod
    def build(self, context):
        pass

    def execute(self, context):
        return supervise(self.build(context), context.run_dir / "logs" / "solver.log")

    @abstractmethod
    def postprocess(self, context):
        pass
