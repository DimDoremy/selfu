"""System configuration checks: shell rc/profile files, systemd state, hostname."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ShellConfigInfo:
    files: list[tuple[str, bool, int]] = field(default_factory=list)
    """(path, exists, size_in_bytes) for each candidate shell config."""

    @property
    def existing(self) -> list[str]:
        return [p for p, exists, _ in self.files if exists]


@dataclass
class SystemdUnit:
    name: str
    load: str
    active: str
    sub: str
    description: str
    # Resolved unit-file location (filled in for failed units).
    fragment_path: str = ""        # path to the unit file (may be empty for transient/generated)
    location: str = "none"         # etc | usr | run | other | none

    @property
    def writable(self) -> bool:
        """Whether the unit file can be edited directly.

        On immutable/ostree systems ``/usr`` is read-only, so units shipped in
        the image (``/usr/lib/systemd/system/``) can only be overridden via a
        drop-in under ``/etc/systemd/system/<unit>.d/``.
        """
        return self.location in ("etc", "other", "none")


@dataclass
class SystemdInfo:
    failed: list[SystemdUnit] = field(default_factory=list)
    enabled: list[str] = field(default_factory=list)
    state: str = ""
    immutable: bool = False        # host is an immutable/ostree system
    raw_failed: str = ""
    raw_enabled: str = ""

    @property
    def healthy(self) -> bool:
        return not self.failed


@dataclass
class HostInfo:
    hostname: str = ""
    static_hostname: str = ""
    os: str = ""
    kernel: str = ""
    architecture: str = ""
    virtualization: str = ""
    raw: str = ""


@dataclass
class SystemInfo:
    shell: ShellConfigInfo = field(default_factory=ShellConfigInfo)
    systemd: SystemdInfo = field(default_factory=SystemdInfo)
    host: HostInfo = field(default_factory=HostInfo)


SHELL_CONFIG_CANDIDATES: tuple[str, ...] = (
    "~/.bashrc",
    "~/.bash_profile",
    "~/.profile",
    "~/.zshrc",
    "~/.zprofile",
    "~/.config/fish/config.fish",
    "/etc/profile",
    "/etc/bash.bashrc",
)


def check_shell_config() -> ShellConfigInfo:
    """Discover and stat common shell rc/profile files."""
    info = ShellConfigInfo()
    for candidate in SHELL_CONFIG_CANDIDATES:
        path = Path(os.path.expanduser(candidate))
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        info.files.append((candidate, exists, size))
    return info


def is_immutable_system() -> bool:
    """Heuristic: an ostree-booted image or a read-only /usr mount.

    Covers Silverblue/Kinoite/Bazzite/CoreOS and other image-based distros
    where ``/usr/lib/systemd/system/`` is not directly editable.
    """
    if Path("/run/ostree-booted").exists():
        return True
    # /usr mounted read-only is a strong immutable signal too.
    try:
        with open("/proc/mounts") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "/usr" and "ro," in f"{parts[3]},":
                    return True
    except OSError:
        pass
    return False


def _classify_fragment_path(path: str) -> str:
    if not path:
        return "none"
    if path.startswith("/etc/"):
        return "etc"
    if path.startswith("/usr/"):
        return "usr"
    if path.startswith("/run/"):
        return "run"
    return "other"


def _resolve_fragment_path(unit_name: str) -> tuple[str, str]:
    """Resolve a unit's FragmentPath via systemctl; return (path, location)."""
    from ..runner import run_optional

    res = run_optional(["systemctl", "show", unit_name, "-p", "FragmentPath", "--value"])
    if res is None or not res.ok:
        return "", "none"
    # systemctl prints one FragmentPath per line; transient/generated units are empty.
    path = res.stdout.strip().splitlines()[0].strip() if res.stdout.strip() else ""
    return path, _classify_fragment_path(path)


def check_systemd() -> SystemdInfo:
    """Use ``systemctl`` to list failed and enabled units.

    For each *failed* unit the fragment path is resolved via
    ``systemctl show -p FragmentPath`` so that, on immutable systems, the user
    can tell read-only image units (``/usr/lib/systemd/system/``) from editable
    ones (``/etc/systemd/system/``) and knows to use a drop-in override.
    """
    from ..runner import run, run_optional, CommandError

    info = SystemdInfo(immutable=is_immutable_system())
    if run_optional(["systemctl", "--version"]) is None:
        return info

    is_systemd = run_optional(["systemctl", "is-system-running"])
    if is_systemd is not None:
        info.state = is_systemd.output

    try:
        failed = run(
            ["systemctl", "list-units", "--state=failed", "--plain", "--no-legend", "--no-pager"],
            timeout=10,
        )
        info.raw_failed = failed.stdout.strip()
        for line in failed.stdout.splitlines():
            parts = line.split(maxsplit=4)
            if len(parts) < 4:
                continue
            name, load, active, sub = parts[:4]
            desc = parts[4] if len(parts) > 4 else ""
            unit = SystemdUnit(name, load, active, sub, desc)
            path, location = _resolve_fragment_path(name)
            unit.fragment_path = path
            unit.location = location
            info.failed.append(unit)
    except CommandError:
        pass

    try:
        enabled = run(
            ["systemctl", "list-unit-files", "--state=enabled", "--plain", "--no-legend", "--no-pager"],
            timeout=10,
        )
        info.raw_enabled = enabled.stdout.strip()
        for line in enabled.stdout.splitlines():
            parts = line.split()
            if parts:
                info.enabled.append(parts[0])
    except CommandError:
        pass

    return info


def check_host() -> HostInfo:
    """Collect host identity via ``hostnamectl`` (fallback to uname)."""
    from ..runner import run, run_optional

    info = HostInfo()
    hc = run_optional(["hostnamectl", "status"])
    if hc is not None and hc.ok:
        info.raw = hc.stdout.strip()
        mapping = {}
        for line in hc.stdout.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                mapping[key.strip().lower().replace(" ", "_")] = value.strip()
        info.static_hostname = mapping.get("static_hostname", "")
        info.hostname = mapping.get("transient_hostname", info.static_hostname)
        info.os = mapping.get("operating_system", "")
        info.kernel = mapping.get("kernel", "")
        info.architecture = mapping.get("architecture", "")
        info.virtualization = mapping.get("virtualization", "")
        return info

    uname = run(["uname", "-srm"])
    parts = uname.output.split()
    if len(parts) >= 3:
        info.kernel = parts[1]
        info.architecture = parts[2]
    info.os = parts[0] if parts else ""
    return info


def check_all() -> SystemInfo:
    return SystemInfo(
        shell=check_shell_config(),
        systemd=check_systemd(),
        host=check_host(),
    )
