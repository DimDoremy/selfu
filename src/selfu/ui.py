"""Rich renderables for each check result.

These functions turn the structured data from :mod:`selfu.checks` into Rich
panels/tables so they can be reused by both the Typer CLI and the Textual TUI.
"""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .checks import cpu as cpu_mod
from .checks import disk as disk_mod
from .checks import health as health_mod
from .checks import memory as mem_mod
from .checks import network as net_mod
from .checks import security as sec_mod
from .checks import system as sys_mod
from .checks import updates as upd_mod


def _status(value: bool, ok_label: str = "OK", bad_label: str = "FAIL") -> Text:
    return Text(ok_label if value else bad_label, style="green" if value else "bold red")


def _bar(percent: float, width: int = 20) -> Text:
    filled = max(0, min(width, round(percent / 100 * width)))
    bar = "█" * filled + "░" * (width - filled)
    color = "green" if percent < 70 else "yellow" if percent < 90 else "red"
    return Text(f"{bar} {percent:5.1f}%", style=color)


def render_dns(info: net_mod.DnsInfo) -> Panel:
    title = "DNS"
    if not info.ok:
        body = Text("No DNS servers detected", style="yellow")
    else:
        table = Table.grid(padding=(0, 1))
        table.add_row("Servers:", Text(", ".join(info.servers) or "-", style="cyan"))
        if info.domain:
            table.add_row("Domain:", Text(info.domain, style="cyan"))
        body = table
    return Panel(body, title=title, border_style="cyan" if info.ok else "red")


def render_connectivity(info: net_mod.ConnectivityInfo) -> Panel:
    lines = [
        Text.assemble("Target: ", Text(info.target, style="cyan")),
        Text.assemble("Reachable: ", _status(info.reachable)),
    ]
    if info.detail:
        lines.append(Text(info.detail, style="dim"))
    body = Text("\n").join(lines)
    return Panel(body, title="Connectivity", border_style="green" if info.reachable else "red")


def render_wifi(info: net_mod.WifiInfo) -> Panel:
    from rich.console import Group

    if not info.enabled:
        body = Text("Wi-Fi radio disabled", style="yellow")
    elif not info.networks:
        body = Group(
            Text.assemble("Connected: ", _status(bool(info.connected_ssid))),
            Text("No networks listed", style="dim"),
        )
    else:
        table = Table.grid(padding=(0, 2))
        table.add_row(
            Text("SSID", style="bold"),
            Text("Signal", style="bold"),
            Text("Security", style="bold"),
        )
        for net in info.networks[:8]:
            ssid_text = Text(net.ssid)
            if net.connected:
                ssid_text.stylize("bold green")
                ssid_text.append(" *", style="green")
            table.add_row(ssid_text, Text(f"{net.signal}%"), Text(net.security))
        connected_line = Text.assemble("Connected: ", _status(info.ok, info.connected_ssid or "-", "—"))
        body = Group(connected_line, Text(""), table)
    return Panel(body, title=f"Wi-Fi ({'on' if info.enabled else 'off'})", border_style="magenta")


def render_firewall(info: net_mod.FirewallInfo) -> Panel:
    lines = [
        Text.assemble("Backend: ", Text(info.backend, style="cyan")),
        Text.assemble("Running: ", _status(info.running, "yes", "no")),
    ]
    if info.services:
        lines.append(Text.assemble("Services: ", Text(", ".join(info.services), style="cyan")))
    if info.zones:
        lines.append(Text.assemble("Zones: ", Text(", ".join(info.zones), style="cyan")))
    body = Text("\n").join(lines)
    color = "red" if (info.backend == "none" or not info.running) else "yellow"
    return Panel(body, title="Firewall", border_style=color)


def render_network(networks: dict) -> Panel:
    from rich.console import Group

    parts = [
        render_dns(networks["dns"]),
        render_resolve(networks["resolve"]) if "resolve" in networks else None,
        render_connectivity(networks["connectivity"]),
        render_wifi(networks["wifi"]),
        render_firewall(networks["firewall"]),
        render_ports(networks["ports"]) if "ports" in networks else None,
    ]
    return Panel(Group(*[p for p in parts if p is not None]), title="Network", border_style="blue")


def render_disk(info: disk_mod.DiskInfo) -> Panel:
    table = Table(expand=True, show_lines=False)
    table.add_column("Filesystem", style="cyan", no_wrap=True)
    table.add_column("Size", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Avail", justify="right")
    table.add_column("Use%", justify="left")
    table.add_column("Mounted on", style="dim")

    for fs in info.filesystems:
        table.add_row(
            fs.filesystem,
            fs.size,
            fs.used,
            fs.avail,
            _bar(fs.use_percent, width=14),
            fs.mount,
        )
    return Panel(table, title="Disk usage", border_style="green")


def render_memory(info: mem_mod.MemoryInfo) -> Panel:
    h = info.human_fields
    table = Table.grid(padding=(0, 2))
    table.add_row(Text("Memory", style="bold"), _bar(info.use_percent))
    table.add_row("Total", h.get("total", "-"))
    table.add_row("Used", h.get("used", "-"))
    table.add_row("Available", h.get("available", "-"))
    table.add_row("Buff/Cache", h.get("buff_cache", "-"))
    table.add_row("Shared", h.get("shared", "-"))
    table.add_row(Text("Swap", style="bold"), _bar(info.swap_use_percent) if info.swap_total else Text("disabled", style="dim"))
    if info.swap_total:
        table.add_row("Swap total", h.get("swap_total", "-"))
        table.add_row("Swap used", h.get("swap_used", "-"))
    return Panel(table, title="Memory", border_style="yellow")


def render_shell_config(info: sys_mod.ShellConfigInfo) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_row(Text("Config file", style="bold"), Text("Exists", style="bold"), Text("Size", style="bold"))
    for path, exists, size in info.files:
        marker = _status(exists, "yes", "no")
        size_text = Text(f"{size} B") if exists else Text("—", style="dim")
        style = "green" if exists else "dim"
        table.add_row(Text(path, style=style), marker, size_text)
    return Panel(table, title="Shell rc/profile", border_style="cyan")


def render_systemd(info: sys_mod.SystemdInfo) -> Panel:
    from rich.console import Group

    lines = [
        Text.assemble("State: ", Text(info.state or "unknown", style="cyan")),
        Text.assemble("Failed units: ", _status(info.healthy, "none", f"{len(info.failed)}")),
    ]
    if info.immutable:
        lines.append(Text.assemble(
            "Host: ", Text("immutable/ostree", style="yellow"),
            Text("  (units in /usr/lib/systemd/system/ are read-only; override with ", style="dim"),
            Text("systemctl edit <unit>", style="cyan"),
            Text(")", style="dim"),
        ))
    if info.failed:
        table = Table.grid(padding=(0, 2))
        table.add_row(
            Text("Unit", style="bold"),
            Text("Active", style="bold"),
            Text("Fragment path", style="bold"),
            Text("Description", style="bold"),
        )
        for unit in info.failed[:10]:
            # Colour the path by writability: green=editable, red=read-only (immutable image),
            # dim=transient/generated (no fragment file).
            if unit.location == "usr":
                path_text = Text(unit.fragment_path or "(read-only image)", style="red")
                hint = "  \u2192 systemctl edit " + unit.name
                path_text.append(hint, style="cyan")
            elif unit.location == "none":
                path_text = Text("transient/generated", style="dim")
            else:
                path_text = Text(unit.fragment_path or "-", style="green")
            table.add_row(
                Text(unit.name, style="red"),
                Text(unit.active, style="red"),
                path_text,
                Text(unit.description, style="dim"),
            )
        body = Group(Text("\n").join(lines), Text(""), table)
    else:
        enabled_count = len(info.enabled)
        lines.append(Text.assemble("Enabled units: ", Text(str(enabled_count), style="cyan")))
        body = Text("\n").join(lines)
    color = "green" if info.healthy else "red"
    return Panel(body, title="systemd", border_style=color)


def render_host(info: sys_mod.HostInfo) -> Panel:
    table = Table.grid(padding=(0, 2))
    rows = [
        ("Hostname", info.hostname),
        ("Static hostname", info.static_hostname),
        ("OS", info.os),
        ("Kernel", info.kernel),
        ("Architecture", info.architecture),
        ("Virtualization", info.virtualization or "none"),
    ]
    for label, value in rows:
        table.add_row(Text(label, style="bold"), Text(value or "-", style="cyan"))
    return Panel(table, title="Host", border_style="blue")


# ---------------------------------------------------------------------------
# New checks
# ---------------------------------------------------------------------------


def _human_uptime(seconds: float) -> str:
    if seconds <= 0:
        return "-"
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def render_cpu(info: cpu_mod.CpuInfo) -> Panel:
    load_color = "green" if not info.busy else "yellow" if info.load_per_core < 1.5 else "red"
    header = Table.grid(padding=(0, 2))
    header.add_row(
        Text("Cores", style="bold"), Text(str(info.cores), style="cyan"),
        Text("Load 1/5/15", style="bold"),
        Text(f"{info.load1:.2f} / {info.load5:.2f} / {info.load15:.2f}", style=load_color),
    )
    header.add_row(
        Text("Load/core", style="bold"), Text(f"{info.load_per_core:.2f}", style=load_color),
        Text("Procs (run/total)", style="bold"),
        Text(f"{info.running_procs} / {info.total_procs}", style="cyan"),
    )
    header.add_row(
        Text("Uptime", style="bold"), Text(_human_uptime(info.uptime_seconds), style="cyan"),
        Text("", style="bold"), Text(""),
    )

    def _proc_table(title: str, procs: list[cpu_mod.ProcessInfo], accent: str) -> Table:
        t = Table.grid(padding=(0, 2))
        t.add_row(Text("PID", style="bold"), Text("User", style="bold"),
                  Text("%CPU", style="bold"), Text("%MEM", style="bold"), Text("Command", style="bold"))
        for p in procs:
            t.add_row(Text(str(p.pid)), Text(p.user),
                      Text(f"{p.cpu:.1f}", style=accent), Text(f"{p.mem:.1f}"), Text(p.command, style="cyan"))
        return t

    body = Group(
        header,
        Text(""),
        Text("Top CPU", style="bold"),
        _proc_table("Top CPU", info.top_cpu, "yellow"),
        Text(""),
        Text("Top MEM", style="bold"),
        _proc_table("Top MEM", info.top_mem, "magenta"),
    ) if info.top_cpu or info.top_mem else header
    return Panel(body, title="CPU & load", border_style="blue")


def render_inodes(info: disk_mod.InodeInfo) -> Panel:
    table = Table(expand=True)
    table.add_column("Filesystem", style="cyan", no_wrap=True)
    table.add_column("Inodes", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Free", justify="right")
    table.add_column("IUse%", justify="left")
    table.add_column("Mounted on", style="dim")
    for fs in info.filesystems:
        table.add_row(fs.filesystem, str(fs.inodes), str(fs.used), str(fs.free),
                      _bar(fs.use_percent, width=14), fs.mount)
    return Panel(table, title="Inode usage", border_style="green")


def render_resolve(info: net_mod.ResolveInfo) -> Panel:
    lines = [
        Text.assemble("Domain: ", Text(info.domain, style="cyan")),
        Text.assemble("Resolved: ", _status(info.resolved)),
    ]
    if info.addresses:
        lines.append(Text.assemble("Addresses: ", Text(", ".join(info.addresses), style="green")))
    if info.detail:
        lines.append(Text(info.detail, style="dim"))
    body = Text("\n").join(lines)
    return Panel(body, title="DNS resolution", border_style="green" if info.resolved else "red")


def render_ports(info: net_mod.PortsInfo) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_row(Text("Proto", style="bold"), Text("Local", style="bold"),
                  Text("Bind", style="bold"), Text("Process", style="bold"))
    for s in info.listening:
        bind_style = "yellow" if s.bind in ("*", "0.0.0.0", "::") and s.bind not in ("127.0.0.1", "::1") else "cyan"
        table.add_row(Text(s.proto), Text(s.address, style=bind_style),
                      Text(s.bind, style="dim"), Text(s.process, style="green"))
    public = len(info.public_listeners)
    summary = Text.assemble(
        "Listening: ", Text(str(len(info.listening)), style="cyan"),
        "  |  Public: ", Text(str(public), style="red" if public else "green"),
        "  |  Established: ", Text(str(info.established), style="cyan"),
        "  |  TIME_WAIT: ", Text(str(info.time_wait), style="dim"),
    )
    body = Group(summary, Text(""), table) if info.listening else summary
    return Panel(body, title="Listening ports", border_style="magenta")


def render_ntp(info: health_mod.NtpInfo) -> Panel:
    lines = [
        Text.assemble("Backend: ", Text(info.backend, style="cyan")),
        Text.assemble("Synced: ", _status(info.synced, "yes", "no")),
    ]
    if info.source:
        lines.append(Text.assemble("Source: ", Text(info.source, style="cyan")))
    if info.detail:
        lines.append(Text(info.detail, style="dim"))
    body = Text("\n").join(lines)
    return Panel(body, title="NTP / clock", border_style="green" if info.ok else "red")


def render_health(info: health_mod.HealthInfo) -> Panel:
    from rich.console import Group

    boot_text = info.boot_time_text.replace("\n", " | ") if info.boot_time_text else _human_uptime(info.boot_time_seconds)
    head = Table.grid(padding=(0, 2))
    head.add_row(Text("Boot time", style="bold"), Text(boot_text, style="cyan"))
    head.add_row(Text("Uptime", style="bold"), Text(_human_uptime(info.uptime_seconds), style="cyan"))
    head.add_row(Text("Entropy", style="bold"),
                 Text(str(info.entropy), style="green" if info.entropy > 200 else "yellow"))
    head.add_row(Text("Timezone", style="bold"), Text(info.timezone or "-", style="dim"))

    parts: list = [head, Text(""), render_ntp(info.ntp)]

    parts.append(Text(""))
    parts.append(Text.assemble("OOM kills this boot: ", _status(info.oom_health_ok, "none", str(len(info.oom_kills)))))
    if info.oom_kills:
        for line in info.oom_kills[:5]:
            parts.append(Text(f"  {line}", style="red"))

    parts.append(Text(""))
    parts.append(Text.assemble("Errors this boot: ", _status(not info.errors, "none", str(len(info.errors)))))
    if info.errors:
        et = Table.grid(padding=(0, 2))
        et.add_row(Text("When", style="bold"), Text("Unit", style="bold"), Text("Message", style="bold"))
        for e in info.errors[:15]:
            et.add_row(Text(e.time, style="dim"), Text(e.unit, style="yellow"), Text(e.message, style="red"))
        parts.append(et)
    return Panel(Group(*parts), title="Health", border_style="green" if info.healthy else "red")


def render_security(info: sec_mod.SecurityInfo) -> Panel:
    from rich.console import Group

    head = Table.grid(padding=(0, 2))
    mac_color = {"enforcing": "green", "permissive": "yellow", "disabled": "red"}.get(info.mac.mode, "dim")
    head.add_row(Text("MAC", style="bold"), Text(f"{info.mac.backend}: ", style="cyan"),
                 Text(info.mac.mode, style=mac_color))
    def _ssh_color(value: str, hardening_on: bool) -> str:
        v = value.strip().lower()
        if v == "needs root":
            return "dim"
        good = v in {"no"} if hardening_on else v in {"yes"}
        return "green" if good else "red"

    head.add_row(Text("SSH port", style="bold"), Text(info.ssh.port, style="cyan"), Text(""))
    head.add_row(Text("SSH PermitRootLogin", style="bold"),
                 Text(info.ssh.permit_root_login, style=_ssh_color(info.ssh.permit_root_login, False)), Text(""))
    head.add_row(Text("SSH PasswordAuth", style="bold"),
                 Text(info.ssh.password_authentication, style=_ssh_color(info.ssh.password_authentication, True)), Text(""))
    head.add_row(Text("Source", style="bold"), Text(info.ssh.source, style="dim"),
                 Text(info.ssh.detail, style="dim"))

    parts: list = [head, Text("")]
    parts.append(Text.assemble("Failed login attempts: ",
                               _status(info.failed_total == 0, "none", str(info.failed_total) if info.failed_total >= 0 else "n/a")))
    if info.failed_logins:
        ft = Table.grid(padding=(0, 2))
        ft.add_row(Text("When/User/Source", style="bold"))
        for f in info.failed_logins[:10]:
            label = f"{f.when}  {f.user}@{f.source}".strip()
            ft.add_row(Text(label, style="red"))
        parts.append(ft)

    parts.append(Text(""))
    parts.append(Text.assemble("Active sessions: ", Text(str(len(info.sessions)), style="cyan")))
    if info.sessions:
        st = Table.grid(padding=(0, 2))
        st.add_row(Text("User", style="bold"), Text("TTY", style="bold"),
                  Text("From", style="bold"), Text("When", style="bold"))
        for s in info.sessions:
            st.add_row(Text(s.user, style="green"), Text(s.tty, style="cyan"),
                      Text(s.source, style="dim"), Text(s.when, style="dim"))
        parts.append(st)
    return Panel(Group(*parts), title="Security", border_style="magenta")


def render_updates(info: upd_mod.UpdateInfo) -> Panel:
    from rich.console import Group

    head = Table.grid(padding=(0, 2))
    head.add_row(Text("Distro", style="bold"), Text(f"{info.distro_id} ({info.distro_family})", style="cyan"))
    if info.error:
        head.add_row(Text("Error", style="bold"), Text(info.error, style="red"))
    reboot_color = "red" if info.reboot_required else "green"
    head.add_row(Text("Reboot", style="bold"), _status(not info.reboot_required, "not required", "REQUIRED"), )
    head.add_row(Text("Reason", style="bold"), Text(info.reboot_reason or "-", style=reboot_color))

    parts: list = [head, Text("")]
    parts.append(Text.assemble("Upgradable: ", Text(str(len(info.upgradable)), style="yellow" if info.upgradable else "green")))
    if info.upgradable:
        cols = ", ".join(info.upgradable[:40])
        parts.append(Text(cols, style="cyan"))
        if len(info.upgradable) > 40:
            parts.append(Text(f"... and {len(info.upgradable) - 40} more", style="dim"))

    parts.append(Text(""))
    parts.append(Text.assemble("Security: ", Text(str(len(info.security)), style="red" if info.security else "green")))
    if info.security:
        parts.append(Text(", ".join(info.security[:40]), style="red"))
    return Panel(Group(*parts), title="Updates", border_style="yellow")
