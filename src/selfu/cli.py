"""Typer CLI entrypoint for Selfu."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

from . import ui
from .checks import cpu as cpu_checks
from .checks import disk as disk_checks
from .checks import health as health_checks
from .checks import memory as mem_checks
from .checks import network as net_checks
from .checks import security as sec_checks
from .checks import system as sys_checks
from .checks import updates as upd_checks

app = typer.Typer(
    name="selfu",
    help="Selfu - sysadmin self-check toolkit (network, disk, memory, system).",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=True,
)
console = Console()


network_app = typer.Typer(help="Network status (dns, connectivity, wifi, firewall).", no_args_is_help=False)
system_app = typer.Typer(help="System configuration (shell rc, systemd, host).", no_args_is_help=False)
app.add_typer(network_app, name="network")
app.add_typer(system_app, name="system")


@app.callback(invoke_without_command=False)
def _main() -> None:
    """Run a check. Use --help to see subcommands."""


@network_app.callback(invoke_without_command=True)
def network_all(
    ctx: typer.Context,
    all_: bool = typer.Option(True, "--all/--no-all", help="Show every network check."),
) -> None:
    """Inspect network state. With no subcommand, run every check."""
    if ctx.invoked_subcommand is not None:
        return
    if all_:
        result = net_checks.check_all()
        console.print(ui.render_network(result))


@network_app.command("dns")
def network_dns() -> None:
    """Show DNS servers and domain from resolvectl."""
    console.print(ui.render_dns(net_checks.check_dns()))


@network_app.command("connectivity")
def network_connectivity(
    host: str = typer.Option("1.1.1.1", "--host", "-H", help="Host to ping."),
) -> None:
    """Ping a host to verify connectivity."""
    console.print(ui.render_connectivity(net_checks.check_connectivity(host)))


@network_app.command("wifi")
def network_wifi() -> None:
    """List Wi-Fi state and nearby networks via nmcli."""
    console.print(ui.render_wifi(net_checks.check_wifi()))


@network_app.command("firewall")
def network_firewall() -> None:
    """Report firewall backend and running state."""
    console.print(ui.render_firewall(net_checks.check_firewall()))


@network_app.command("ports")
def network_ports() -> None:
    """List listening sockets and connection-state summary (ss)."""
    console.print(ui.render_ports(net_checks.check_ports()))


@network_app.command("resolve")
def network_resolve(
    domain: str = typer.Argument("example.com", help="Domain name to resolve."),
) -> None:
    """Verify a domain actually resolves (not just listing DNS servers)."""
    console.print(ui.render_resolve(net_checks.check_resolve(domain)))


@app.command()
def disk(
    raw: bool = typer.Option(False, "--raw", help="Print raw df output."),
    inodes: bool = typer.Option(False, "--inode", "-i", help="Also show inode usage (df -i)."),
) -> None:
    """Show disk usage from df."""
    from rich.console import Group

    info = disk_checks.check_disk()
    if raw and not inodes:
        console.print(info.raw)
        return
    if inodes:
        inode_info = disk_checks.check_inodes()
        if raw:
            console.print(inode_info.raw)
            return
        console.print(Group(ui.render_disk(info), ui.render_inodes(inode_info)))
    else:
        console.print(ui.render_disk(info))


@app.command()
def memory(
    raw: bool = typer.Option(False, "--raw", help="Print raw free output."),
) -> None:
    """Show memory usage from free."""
    info = mem_checks.check_memory()
    if raw:
        console.print(info.raw)
    else:
        console.print(ui.render_memory(info))


@app.command()
def cpu(
    top: int = typer.Option(8, "--top", "-n", help="How many top processes to list."),
) -> None:
    """Show CPU load average, uptime and top processes."""
    console.print(ui.render_cpu(cpu_checks.check_cpu(top=top)))


@app.command()
def health(
    limit: int = typer.Option(30, "--limit", help="Max journal error entries to parse."),
) -> None:
    """Show boot errors, OOM kills, boot time, NTP sync and entropy."""
    console.print(ui.render_health(health_checks.check_all(limit=limit)))


@app.command()
def security() -> None:
    """Show failed logins, sessions, MAC and SSH effective config."""
    console.print(ui.render_security(sec_checks.check_all()))


@app.command()
def updates() -> None:
    """Show pending updates, security advisories and reboot status."""
    console.print(ui.render_updates(upd_checks.check_updates()))


@system_app.callback(invoke_without_command=True)
def system_all(ctx: typer.Context) -> None:
    """Show all system configuration info. With no subcommand, run every check."""
    if ctx.invoked_subcommand is not None:
        return
    from rich.console import Group

    info = sys_checks.check_all()
    console.print(Panel(Group(
        ui.render_shell_config(info.shell),
        ui.render_systemd(info.systemd),
        ui.render_host(info.host),
    ), title="System", border_style="blue"))


@system_app.command("shell")
def system_shell() -> None:
    """Inspect shell rc/profile files."""
    console.print(ui.render_shell_config(sys_checks.check_shell_config()))


@system_app.command("systemd")
def system_systemd() -> None:
    """List failed/enabled systemd units."""
    console.print(ui.render_systemd(sys_checks.check_systemd()))


@system_app.command("host")
def system_host() -> None:
    """Show host identity from hostnamectl."""
    console.print(ui.render_host(sys_checks.check_host()))


@app.command()
def all() -> None:
    """Run every check and print a consolidated report."""
    from rich.console import Group

    net = net_checks.check_all()
    console.print(ui.render_network(net))
    console.print(ui.render_cpu(cpu_checks.check_cpu()))
    console.print(ui.render_disk(disk_checks.check_disk()))
    console.print(ui.render_memory(mem_checks.check_memory()))
    sysinfo = sys_checks.check_all()
    console.print(Panel(Group(
        ui.render_shell_config(sysinfo.shell),
        ui.render_systemd(sysinfo.systemd),
        ui.render_host(sysinfo.host),
    ), title="System", border_style="blue"))
    console.print(ui.render_health(health_checks.check_all()))
    console.print(ui.render_security(sec_checks.check_all()))
    console.print(ui.render_updates(upd_checks.check_updates()))


@app.command()
def dashboard() -> None:
    """Launch the interactive Textual dashboard."""
    from .tui import SelfuDashboard

    SelfuDashboard().run()


@app.command()
def completions(
    shell: str = typer.Argument(..., help="Target shell: bash, zsh, fish, powershell, pwsh."),
    install: bool = typer.Option(
        False,
        "--install",
        help="Write the script to the shell's standard location instead of printing it.",
    ),
) -> None:
    """Print or install the shell-completion script for selfu.

    \b
    Examples:
      selfu completions bash                 # print script (pipe into a file / eval)
      eval "$(selfu completions bash)"       # enable for the current bash session
      selfu completions fish --install       # install permanently
    """
    from . import completions as comp_mod

    if shell not in comp_mod.SUPPORTED:
        raise typer.BadParameter(
            f"unsupported shell {shell!r}; choose from {', '.join(comp_mod.SUPPORTED)}"
        )

    if install:
        try:
            path = comp_mod.install(shell)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        console.print(f"[green]Installed[/] {shell} completion -> [cyan]{path}[/]")
        hint = comp_mod.hint(shell, path)
        if hint:
            console.print(hint, style="dim")
    else:
        # Print raw script - must disable rich markup/highlight so it stays source-clean.
        console.print(comp_mod.generate(shell), markup=False, highlight=False, soft_wrap=True)


if __name__ == "__main__":
    app()
