from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class RunStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    PREPROCESSING = "PREPROCESSING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    POSTPROCESSING = "POSTPROCESSING"
    SUCCEEDED = "SUCCEEDED"
    TIMEOUT = "TIMEOUT"
    CRASHED = "CRASHED"
    INFRA_ERROR = "INFRA_ERROR"
    UNSUPPORTED = "UNSUPPORTED"
    CANCELLED = "CANCELLED"


@dataclass
class Command:
    argv: List[str]
    cwd: Path
    env: Dict[str, str]
    timeout: float = 300
    heartbeat_timeout: Optional[float] = 120


@dataclass
class StageResult:
    status: str = "SUCCEEDED"
    message: str = ""
    artifacts: List[str] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    elapsed: float = 0
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SolverInfo:
    name: str
    version: str
    build: str
    branch: str
    capabilities: List[str]
    executables: Dict[str, str]


@dataclass
class RunContext:
    root: Path
    case_path: Path
    run_dir: Path
    case: Dict[str, Any]
    condition: Dict[str, Any]
    condition_id: str
    parameters: Dict[str, Any]
    execution: Dict[str, Any]
    installation: Dict[str, Any]
    environment: Dict[str, str]
    info: SolverInfo
    timeout: float = 300
    heartbeat_timeout: Optional[float] = 120
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    manifest: Dict[str, Any] = field(default_factory=dict)

    @property
    def work(self):
        return self.run_dir / "work"

    @property
    def input(self):
        return self.run_dir / "input"

    @property
    def normalized(self):
        return self.run_dir / "normalized"


@dataclass
class MonitorRecord:
    monitor: str
    step: int
    time: Optional[float]
    value: float
    unit: str = ""
    quality: str = "valid"


@dataclass
class FieldMesh:
    points: List[Any]
    cells: List[Any]
    types: List[int]
    domain: str


@dataclass
class FieldDataset:
    time: float
    domain: str
    field: str
    unit: str
    samples: List[Any]
    file: str


@dataclass
class FieldSample:
    cell_id: int
    center: List[float]
    volume: float
    value: List[float]


@dataclass
class FieldComparisonResult:
    reference: str
    field: str
    domain: str
    time: float
    component: str
    status: str
    statistics: Dict[str, Any]
