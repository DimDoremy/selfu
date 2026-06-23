"""Memory consumption check using native ``free``."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryInfo:
    total: int = 0
    used: int = 0
    free: int = 0
    shared: int = 0
    buff_cache: int = 0
    available: int = 0
    swap_total: int = 0
    swap_used: int = 0
    swap_free: int = 0
    raw: str = ""

    @property
    def use_percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return (self.used / self.total) * 100.0

    @property
    def swap_use_percent(self) -> float:
        if self.swap_total <= 0:
            return 0.0
        return (self.swap_used / self.swap_total) * 100.0

    @property
    def human_fields(self) -> dict[str, str]:
        return _humanize(self.raw)


def _humanize(raw: str) -> dict[str, str]:
    """Return the human-readable strings produced by ``free -h``."""
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if line.lower().startswith("mem:"):
            parts = line.split()
            if len(parts) >= 7:
                fields.update(
                    {
                        "total": parts[1],
                        "used": parts[2],
                        "free": parts[3],
                        "shared": parts[4],
                        "buff_cache": parts[5],
                        "available": parts[6],
                    }
                )
        elif line.lower().startswith("swap:"):
            parts = line.split()
            if len(parts) >= 4:
                fields.update(
                    {
                        "swap_total": parts[1],
                        "swap_used": parts[2],
                        "swap_free": parts[3],
                    }
                )
    return fields


def check_memory() -> MemoryInfo:
    """Parse ``free`` output (in kibibytes) into a structured view."""
    from ..runner import run

    raw_struct = run(["free", "--kibi"], timeout=10)
    raw_human = run(["free", "--human"], timeout=10)
    info = MemoryInfo(raw=raw_human.stdout.strip())

    for line in raw_struct.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        key = parts[0].rstrip(":").lower()
        if key == "mem" and len(parts) >= 7:
            info.total = int(parts[1])
            info.used = int(parts[2])
            info.free = int(parts[3])
            info.shared = int(parts[4])
            info.buff_cache = int(parts[5])
            info.available = int(parts[6])
        elif key == "swap" and len(parts) >= 4:
            info.swap_total = int(parts[1])
            info.swap_used = int(parts[2])
            info.swap_free = int(parts[3])
    return info
