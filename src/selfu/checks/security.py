"""Security checks: failed logins, sessions, MAC, SSH effective config."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FailedLogin:
    user: str
    tty: str
    source: str
    when: str


@dataclass
class Session:
    user: str
    tty: str
    source: str
    when: str
    idle: str = ""


@dataclass
class MacInfo:
    backend: str = "none"     # selinux / apparmor / none
    mode: str = "unknown"     # enforcing / permissive / disabled
    detail: str = ""


@dataclass
class SshConfigInfo:
    permit_root_login: str = "unknown"
    password_authentication: str = "unknown"
    port: str = "unknown"
    source: str = "runtime"   # runtime (sshd -T) / parsed-file
    detail: str = ""


@dataclass
class SecurityInfo:
    failed_logins: list[FailedLogin] = field(default_factory=list)
    failed_total: int = -1     # -1 = unknown
    sessions: list[Session] = field(default_factory=list)
    mac: MacInfo = field(default_factory=MacInfo)
    ssh: SshConfigInfo = field(default_factory=SshConfigInfo)


def check_failed_logins(limit: int = 15) -> tuple[list[FailedLogin], int]:
    """Try lastb (needs btmp read), fall back to sshd journal entries."""
    from ..runner import run, run_optional, CommandError

    # lastb reads /var/log/btmp (root:utmp 0660) - usually needs privileges.
    lastb = run_optional(["lastb", "-n", str(limit), "-F"])
    if lastb is not None and lastb.ok and lastb.stdout.strip():
        logins: list[FailedLogin] = []
        for line in lastb.stdout.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith(("wtmp", "btmp", "reboot", "--"))
                or "no entries" in stripped.lower()
            ):
                continue
            parts = stripped.split()
            if len(parts) < 4:
                continue
            logins.append(FailedLogin(user=parts[0], tty=parts[1], source=parts[2], when=" ".join(parts[3:])))
        return logins, len(logins)

    # Fallback: scan sshd journal for authentication failures.
    journal = run_optional([
        "journalctl",
        "-b",
        "--no-pager",
        "-g",
        r"Failed password|Invalid user|authentication failure|Connection closed by authenticating",
    ])
    messages: list[str] = []
    if journal is not None:
        for line in journal.stdout.splitlines():
            stripped = line.strip()
            if stripped and "no entries" not in stripped.lower() and not stripped.startswith("--"):
                messages.append(stripped)
    return [FailedLogin(user="", tty="", source="", when=m) for m in messages[-limit:]], len(messages)


def check_sessions() -> list[Session]:
    """Use ``who`` to list currently logged-in sessions."""
    from ..runner import run, CommandError

    try:
        result = run(["who"], timeout=5)
    except CommandError:
        return []
    sessions: list[Session] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        user, tty = parts[0], parts[1]
        date = " ".join(parts[2:5])
        source = parts[4] if len(parts) > 4 else ""
        if source.startswith("("):
            source = source.strip("()")
        idle = parts[5] if len(parts) > 5 else ""
        sessions.append(Session(user=user, tty=tty, source=source, when=date, idle=idle))
    return sessions


def check_mac() -> MacInfo:
    """Probe SELinux first (RHEL/Fedora), then AppArmor (Debian/Ubuntu)."""
    from ..runner import run_optional

    getenforce = run_optional(["getenforce"])
    if getenforce is not None:
        mode = getenforce.output or "Disabled"
        info = MacInfo(backend="selinux", mode=mode.lower(), detail=getenforce.output)
        sestatus = run_optional(["sestatus", "-v"])
        if sestatus is not None:
            for line in sestatus.stdout.splitlines():
                if "loaded policy" in line.lower() or "policy version" in line.lower():
                    info.detail += " | " + line.strip()
                    break
        return info

    aa = run_optional(["aa-status"])
    if aa is not None and aa.ok:
        info = MacInfo(backend="apparmor", mode="enabled", detail=aa.stdout.strip().splitlines()[0] if aa.stdout else "")
        for line in aa.stdout.splitlines():
            if "profiles are loaded" in line:
                info.detail = line.strip()
                break
        return info

    return MacInfo(backend="none", mode="n/a", detail="no MAC framework detected")


def check_ssh_config() -> SshConfigInfo:
    """Prefer ``sshd -T`` (runtime, needs root), fall back to parsing the file."""
    import re

    from ..runner import run, run_optional, CommandError

    NEEDS_ROOT = "needs root"
    # sshd -T reads host keys and normally needs root.
    runtime = run_optional(["sshd", "-T"])
    if runtime is not None and runtime.ok:
        info = SshConfigInfo(source="runtime")
        for line in runtime.stdout.splitlines():
            low = line.lower().strip()
            if low.startswith("permitrootlogin "):
                info.permit_root_login = low.split(None, 1)[1]
            elif low.startswith("passwordauthentication "):
                info.password_authentication = low.split(None, 1)[1]
            elif low.startswith("port "):
                info.port = low.split(None, 1)[1]
        return info

    # Fallback: parse /etc/ssh/sshd_config (last definition wins, ignoring Include).
    info = SshConfigInfo(source="parsed-file")
    path = Path("/etc/ssh/sshd_config")
    content: str | None = None
    if path.exists():
        try:
            content = path.read_text(errors="replace")
        except OSError:
            content = None

    if content is not None:
        last: dict[str, str] = {}
        for raw in content.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition(" ")
            last[key.lower()] = value.strip()
        info.permit_root_login = last.get("permitrootlogin", "prohibit-password")
        info.password_authentication = last.get("passwordauthentication", "yes")
        info.port = last.get("port", "22")
        info.detail = f"parsed {path} (Include directives not followed)"
    else:
        # Both runtime and file unreadable -> needs privileges.
        info.permit_root_login = NEEDS_ROOT
        info.password_authentication = NEEDS_ROOT
        info.port = NEEDS_ROOT
        info.source = "unavailable"
        info.detail = "sshd -T and sshd_config both require root to read"
    return info


def check_all() -> SecurityInfo:
    info = SecurityInfo()
    logins, total = check_failed_logins()
    info.failed_logins = logins
    info.failed_total = total
    info.sessions = check_sessions()
    info.mac = check_mac()
    info.ssh = check_ssh_config()
    return info
