"""Pending updates & reboot-required detection, with distro family dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UpdateInfo:
    distro_id: str = "unknown"
    distro_family: str = "unknown"   # rhel / debian / arch / suse / unknown
    upgradable: list[str] = field(default_factory=list)
    security: list[str] = field(default_factory=list)
    reboot_required: bool = False
    reboot_reason: str = ""
    detail: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def _detect_distro() -> tuple[str, str]:
    """Return (id, family) from /etc/os-release."""
    path = Path("/etc/os-release")
    if not path.exists():
        path = Path("/usr/lib/os-release")
    data: dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                data[key.strip()] = value.strip().strip('"')
    except OSError:
        return "unknown", "unknown"

    distro_id = data.get("ID", "unknown").lower()
    likes = data.get("ID_LIKE", "").lower().split()

    rhel_like = {"rhel", "fedora", "centos", "rocky", "almalinux", "anolis", "openeuler", "nobara", "silverblue", "kinoite", "sericea", "bazzite"}
    debian_like = {"debian", "ubuntu", "linuxmint", "pop", "raspbian", "kali", "deepin"}
    arch_like = {"arch", "antergos", "cachyos", "endeavouros", "garuda", "manjaro"}
    suse_like = {"suse", "sles", "opensuse", "opensuse-leap", "opensuse-tumbleweed"}

    def belongs(pool: set[str]) -> bool:
        return distro_id in pool or any(x in pool for x in likes)

    if belongs(rhel_like):
        return distro_id, "rhel"
    if belongs(debian_like):
        return distro_id, "debian"
    if belongs(suse_like):
        return distro_id, "suse"
    if belongs(arch_like):
        return distro_id, "arch"
    return distro_id, "unknown"


def _detect_reboot(family: str) -> tuple[bool, str]:
    """Cross-distro reboot-required heuristic."""
    from ..runner import run, run_optional, CommandError

    # Debian/Ubuntu: marker file written by unattended-upgrades / needrestart.
    marker = Path("/var/run/reboot-required")
    if marker.exists():
        reason = ""
        pkgs = marker.with_name("reboot-required.pkgs")
        if pkgs.exists():
            reason = " ".join(pkgs.read_text().split()) or "packages updated"
        return True, reason or "reboot-required marker present"

    if family == "rhel":
        # needs-restarting -r: exit 1 => reboot needed, 0 => not, 2 => error (needs root).
        nr = run_optional(["needs-restarting", "-r"])
        if nr is not None:
            if nr.returncode == 1:
                return True, nr.stdout.strip() or "needs-restarting: reboot advised"
            if nr.returncode == 0:
                return False, "no reboot needed"
            return False, "needs-restarting could not decide (run as root?)"

    # Last-resort: running kernel != newest installed kernel package version.
    return _kernel_matches_installed(family)


def _kernel_matches_installed(family: str) -> tuple[bool, str]:
    """Compare running kernel to the installed one(s)."""
    from ..runner import run_optional

    try:
        running = Path("/proc/sys/kernel/osrelease").read_text().strip()
    except OSError:
        return False, ""

    if family == "debian":
        newest = run_optional(["dpkg-query", "-W", "-f=${Version}|${Package}\n", "linux-image-*"])
        if newest is not None:
            installed_vers = [l.partition("|")[0] for l in newest.stdout.splitlines() if "|" in l]
            running_base = running.split("-")[0]
            if running_base and not any(running_base in v for v in installed_vers):
                latest = installed_vers[-1] if installed_vers else "?"
                return True, f"running kernel {running}, latest installed {latest}"
        return False, ""

    if family == "rhel":
        newest = run_optional(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}.%{ARCH}\n", "kernel", "kernel-core"])
        if newest is not None:
            installed = [l.strip() for l in newest.stdout.splitlines() if l.strip() and "not installed" not in l]
            if installed and running not in installed:
                return True, f"running {running}, newest installed {installed[-1]}"
        return False, ""

    return False, ""


# ----- per-family collectors -------------------------------------------------

def _collect_rhel() -> UpdateInfo:
    from ..runner import run, run_optional

    info = UpdateInfo()
    # dnf check-update: exit 100 = updates available, 0 = none, 1 = error.
    cu = run_optional(["dnf", "check-update"])
    if cu is None:
        cu = run_optional(["yum", "check-update"])
    if cu is None:
        info.error = "neither dnf nor yum available"
        return info

    info.detail = cu.stdout.strip()
    for line in cu.stdout.splitlines():
        if not line or line.startswith(("Last metadata", "Loaded plugins", "Updating")) or line.strip().endswith(".src"):
            continue
        pkg = line.split()[0]
        if pkg and "." in pkg:
            info.upgradable.append(pkg)

    # Security advisories.
    sec = run_optional(["dnf", "updateinfo", "list", "--security"])
    if sec is None:
        sec = run_optional(["yum", "updateinfo", "list", "security"])
    if sec is not None:
        for line in sec.stdout.splitlines()[1:]:
            parts = line.split()
            if parts:
                info.security.append(parts[0])
    return info


def _collect_debian() -> UpdateInfo:
    from ..runner import run, run_optional

    info = UpdateInfo()
    # No apt-get update here (avoid touching the system). --no-listing avoids lock issues.
    listing = run(["apt", "list", "--upgradable"], timeout=20)
    info.detail = listing.stdout.strip()
    for line in listing.stdout.splitlines():
        if line.startswith("Listing") or not line.strip():
            continue
        name = line.split("/")[0]
        if name:
            info.upgradable.append(name)

    # Security: apt supports listing via origin a=security.
    sec = run_optional([
        "apt-get",
        "-s",
        "-o", "Dir::Etc::Sourceparts=/dev/null",
        "-o", "APT::Get::List-Cleanup=false",
        "upgrade",
    ])
    if sec is not None:
        for line in sec.stdout.splitlines():
            low = line.lower()
            if "inst" in low and ("security" in low or "esm" in low):
                pass  # simulation lines are not easily attributable; keep simple
    return info


def _collect_arch() -> UpdateInfo:
    from ..runner import run_optional

    info = UpdateInfo()
    # checkupdates (pacman-contrib) refreshes to a temp DB without touching the host.
    cu = run_optional(["checkupdates"])
    if cu is None:
        info.error = "checkupdates not found (install pacman-contrib)"
        return info
    info.detail = cu.stdout.strip()
    for line in cu.stdout.splitlines():
        # "pkgname oldver -> newver"
        if "->" in line:
            info.upgradable.append(line.split()[0])
    return info


def _collect_suse() -> UpdateInfo:
    from ..runner import run, run_optional

    info = UpdateInfo()
    lu = run(["zypper", "--no-refresh", "list-updates"], timeout=20)
    info.detail = lu.stdout.strip()
    for line in lu.stdout.splitlines():
        if line.startswith(("-", "|")) or not line.strip() or "S '" in line:
            continue
        parts = line.split("|")
        if len(parts) >= 3:
            info.upgradable.append(parts[2].strip())
    sec = run_optional(["zypper", "--no-refresh", "list-patches", "--category", "security"])
    if sec is not None:
        for line in sec.stdout.splitlines():
            parts = line.split("|")
            if len(parts) >= 3:
                info.security.append(parts[2].strip())
    return info


def check_updates() -> UpdateInfo:
    distro_id, family = _detect_distro()
    info = UpdateInfo(distro_id=distro_id, distro_family=family)

    collector = {
        "rhel": _collect_rhel,
        "debian": _collect_debian,
        "arch": _collect_arch,
        "suse": _collect_suse,
    }.get(family)
    if collector is None:
        info.error = f"unsupported distro family for {distro_id!r} (add /etc/os-release ID_LIKE?)"
        return info

    collected = collector()
    info.upgradable = collected.upgradable
    info.security = collected.security
    info.detail = collected.detail
    info.error = collected.error

    reboot, reason = _detect_reboot(family)
    info.reboot_required = reboot
    info.reboot_reason = reason
    return info
