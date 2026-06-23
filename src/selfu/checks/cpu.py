"""CPU / load / top-process check via /proc, ps, nproc, uptime."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProcessInfo:
    pid: int
    user: str
    cpu: float
    mem: float
    command: str


@dataclass
class CpuInfo:
    cores: int = 0
    load1: float = 0.0
    load5: float = 0.0
    load15: float = 0.0
    running_procs: int = 0
    total_procs: int = 0
    uptime_seconds: float = 0.0
    top_cpu: list[ProcessInfo] = field(default_factory=list)
    top_mem: list[ProcessInfo] = field(default_factory=list)

    @property
    def load_per_core(self) -> float:
        return self.load1 / self.cores if self.cores else self.load1

    @property
    def busy(self) -> bool:
        """Heuristic: 1-min load exceeds the core count."""
        return self.load1 > self.cores > 0


def _read_loadavg() -> tuple[float, float, float, int, int]:
    try:
        text = Path("/proc/loadavg").read_text().split()
        return float(text[0]), float(text[1]), float(text[2]), int(text[3].split("/")[0]), int(text[3].split("/")[1])
    except (OSError, ValueError, IndexError):
        return 0.0, 0.0, 0.0, 0, 0


def _read_uptime() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def _parse_ps(output: str) -> list[ProcessInfo]:
    procs: list[ProcessInfo] = []
    for line in output.splitlines()[1:]:
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        try:
            pid = int(parts[0])
            cpu = float(parts[2])
            mem = float(parts[3])
        except ValueError:
            continue
        procs.append(ProcessInfo(pid=pid, user=parts[1], cpu=cpu, mem=mem, command=parts[4]))
    return procs


def check_cpu(top: int = 8) -> CpuInfo:
    """Collect load average, core count, uptime and top-N processes."""
    from ..runner import run, run_optional

    info = CpuInfo(cores=_detect_cores())
    info.load1, info.load5, info.load15, info.running_procs, info.total_procs = _read_loadavg()
    info.uptime_seconds = _read_uptime()

    fmt = "pid,user,%cpu,%mem,comm"
    top_cpu = run_optional(["ps", "-e", "--no-headers", "-o", fmt, "--sort=-%cpu"])
    if top_cpu is not None:
        info.top_cpu = _parse_ps(top_cpu.stdout)[:top]

    top_mem = run_optional(["ps", "-e", "--no-headers", "-o", fmt, "--sort=-%mem"])
    if top_mem is not None:
        info.top_mem = _parse_ps(top_mem.stdout)[:top]
    return info


def _detect_cores() -> int:
    # Prefer `nproc` (native util), fall back to os.cpu_count, then /proc/cpuinfo.
    import os

    from ..runner import run_optional

    nproc = run_optional(["nproc"])
    if nproc is not None and nproc.ok:
        try:
            return int(nproc.output)
        except ValueError:
            pass
    if os.cpu_count():
        return os.cpu_count() or 0
    try:
        return sum(1 for _ in Path("/proc/cpuinfo").open() if _.startswith("processor"))
    except OSError:
        return 0
