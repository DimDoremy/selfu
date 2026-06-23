"""Boot health: journal errors, OOM kills, boot time, NTP sync, entropy."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class JournalEntry:
    time: str
    host: str
    unit: str
    priority: str
    message: str


@dataclass
class NtpInfo:
    backend: str = "none"        # systemd / chrony / ntp / none
    synced: bool = False
    source: str = ""
    detail: str = ""
    timezone: str = ""

    @property
    def ok(self) -> bool:
        return self.synced


@dataclass
class HealthInfo:
    boot_time_seconds: float = 0.0
    boot_time_text: str = ""
    uptime_seconds: float = 0.0
    ntp: NtpInfo = field(default_factory=NtpInfo)
    entropy: int = 0
    errors: list[JournalEntry] = field(default_factory=list)
    oom_kills: list[str] = field(default_factory=list)
    timezone: str = ""

    @property
    def healthy(self) -> bool:
        return not self.errors and self.oom_health_ok and self.ntp.ok

    @property
    def oom_health_ok(self) -> bool:
        return not self.oom_kills


def _read_uptime() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def _read_entropy() -> int:
    try:
        return int(Path("/proc/sys/kernel/random/entropy_avail").read_text().strip())
    except (OSError, ValueError):
        return -1


def _parse_journal(output: str) -> list[JournalEntry]:
    """Parse ``journalctl -o short-iso`` lines: "TIMESTAMP IDENT[PID]: message"."""
    entries: list[JournalEntry] = []
    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        when, _, rest = line.partition(" ")
        unit, _, message = rest.partition(": ")
        entries.append(
            JournalEntry(time=when, host="", unit=unit or "?", priority="err", message=message or rest)
        )
    return entries


def check_boot_time() -> tuple[float, str]:
    """Run ``systemd-analyze`` and return (seconds, raw_text)."""
    import re

    from ..runner import run_optional

    analyze = run_optional(["systemd-analyze", "time"])
    if analyze is None or not analyze.ok:
        return 0.0, ""
    text = analyze.stdout.strip()
    seconds = 0.0
    # Lines look like: "Startup finished in 3.2s (kernel) + 5.1s ... = 20.6s"
    # Sum up every "<number>(s|ms|min)" token so we get the full wall time.
    for token in text.replace("=", " ").replace("(", " ").replace(")", " ").split():
        m = re.match(r"([\d.]+)(s|ms|min)", token)
        if m:
            value = float(m.group(1))
            unit = m.group(2)
            seconds += value * ({"s": 1, "ms": 0.001, "min": 60}[unit])
    return seconds, text


def check_ntp() -> NtpInfo:
    """Probe NTP sync via timedatectl (fallback chrony/ntp)."""
    from ..runner import run_optional

    info = NtpInfo()
    show = run_optional(["timedatectl", "show"])
    if show is not None and show.ok:
        info.backend = "systemd"
        mapping = {}
        for line in show.stdout.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                mapping[key.strip()] = value.strip()
        info.synced = mapping.get("NTPSynchronized", "no").lower() == "yes"
        ntp_on = mapping.get("NTP", "no").lower() == "yes"
        info.detail = f"NTP={ 'on' if ntp_on else 'off'}, synced={'yes' if info.synced else 'no'}"
        info.timezone = mapping.get("Timezone", "")
        if info.synced:
            info.source = "systemd-timesyncd"
        return info

    chronyc = run_optional(["chronyc", "tracking"])
    if chronyc is not None and chronyc.ok:
        info.backend = "chrony"
        info.synced = False
        info.detail = chronyc.stdout.strip()
        for line in chronyc.stdout.splitlines():
            low = line.lower()
            if low.startswith("leap status"):
                info.synced = "normal" in low
            elif low.startswith("reference id"):
                info.source = line.split(":", 1)[1].strip()
        return info

    ntpstat = run_optional(["ntpstat"])
    if ntpstat is not None:
        info.backend = "ntp"
        info.synced = ntpstat.ok and "synchronised" in ntpstat.stdout.lower()
        info.detail = ntpstat.stdout.strip()
        return info

    return info


def check_errors(limit: int = 30) -> list[JournalEntry]:
    """Gather priority<=err journal entries from the current boot."""
    from ..runner import run_optional

    journal = run_optional(["journalctl", "-p", "err", "-b", "-o", "short-iso", "--no-pager", "--no-hostname"])
    if journal is None:
        return []
    # Drop the trailing "-- No entries --"/hint lines.
    return _parse_journal(journal.stdout)[:limit]


def check_oom() -> list[str]:
    """Find OOM-kill records in the current boot's kernel log."""
    from ..runner import run, run_optional, CommandError

    # Tight pattern: avoid matching the systemd-oomd daemon socket lines.
    pattern = r"Out of memory|out of memory|[Kk]illed process|oom-kill|invoked oom-killer"
    # Prefer journalctl -g (systemd v245+); fall back to Python filtering.
    g = run_optional(["journalctl", "-k", "-b", "--no-pager", "-g", pattern])
    if g is not None:
        text = g.stdout
    else:
        try:
            klog = run(["journalctl", "-k", "-b", "--no-pager"], timeout=15)
            text = "\n".join(
                line for line in klog.stdout.splitlines()
                if any(tok in line for tok in ("Out of memory", "out of memory", "Killed process", "oom-kill"))
            )
        except CommandError:
            text = ""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and "oomd" not in line.lower()
        and "no entries" not in line.lower()
        and not line.strip().startswith("--")
    ][:20]


def check_all(limit: int = 30) -> HealthInfo:
    boot_seconds, boot_text = check_boot_time()
    info = HealthInfo(
        boot_time_seconds=boot_seconds,
        boot_time_text=boot_text,
        uptime_seconds=_read_uptime(),
    )
    info.ntp = check_ntp()
    info.timezone = info.ntp.timezone
    info.entropy = _read_entropy()
    info.errors = check_errors(limit)
    info.oom_kills = check_oom()
    return info
