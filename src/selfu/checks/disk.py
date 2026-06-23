"""Disk usage check using native ``df``."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FilesystemUsage:
    filesystem: str
    size: str
    used: str
    avail: str
    use_percent: int
    mount: str


@dataclass
class DiskInfo:
    filesystems: list[FilesystemUsage] = field(default_factory=list)
    raw: str = ""


@dataclass
class InodeUsage:
    filesystem: str
    inodes: int
    used: int
    free: int
    use_percent: int
    mount: str


@dataclass
class InodeInfo:
    filesystems: list[InodeUsage] = field(default_factory=list)
    raw: str = ""


def check_disk(human: bool = True) -> DiskInfo:
    """Invoke ``df`` to gather mounted filesystem usage."""
    from ..runner import run, CommandError

    cmd = ["df", "--output=source,size,used,avail,pcent,target"]
    if human:
        cmd.insert(1, "-h")
    try:
        result = run(cmd, timeout=10)
    except CommandError:
        result = run(["df", "-h"] if human else ["df"], timeout=10)

    info = DiskInfo(raw=result.stdout.strip())
    lines = result.stdout.splitlines()
    if not lines:
        return info

    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        fs, size, used, avail, pcent, mount = parts[:6]
        try:
            pct = int(pcent.rstrip("%"))
        except ValueError:
            pct = 0
        info.filesystems.append(
            FilesystemUsage(
                filesystem=fs,
                size=size,
                used=used,
                avail=avail,
                use_percent=pct,
                mount=mount,
            )
        )
    return info


def check_inodes() -> InodeInfo:
    """Invoke ``df`` to gather inode usage per mounted filesystem."""
    from ..runner import run, CommandError

    # NB: df refuses to combine -i with --output; the inode --output columns
    # (itotal/iused/iavail/ipcent) already switch it to inode mode on their own.
    cmd = ["df", "--output=source,itotal,iused,iavail,ipcent,target"]
    try:
        result = run(cmd, timeout=10)
    except CommandError:
        result = run(["df", "-i"], timeout=10)

    info = InodeInfo(raw=result.stdout.strip())
    lines = result.stdout.splitlines()
    if not lines:
        return info
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        fs, itotal, iused, iavail, ipcent, mount = parts[:6]
        try:
            total = int(itotal)
            used = int(iused)
            free = int(iavail)
            pct = int(ipcent.rstrip("%"))
        except ValueError:
            continue
        info.filesystems.append(
            InodeUsage(filesystem=fs, inodes=total, used=used, free=free, use_percent=pct, mount=mount)
        )
    return info
