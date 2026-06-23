"""Textual dashboard that aggregates every check in one interactive view."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from . import ui
from .checks import cpu as cpu_checks
from .checks import disk as disk_checks
from .checks import health as health_checks
from .checks import memory as mem_checks
from .checks import network as net_checks
from .checks import security as sec_checks
from .checks import system as sys_checks
from .checks import updates as upd_checks


class SelfuDashboard(App):
    """Interactive Selfu dashboard.

    Keybindings:
      r / R      refresh the active tab
      ctrl+r     refresh everything
      q          quit
    """

    CSS = """
    Screen { layout: vertical; }
    #body { padding: 0 1; }
    TabPane { padding: 0 1; }
    Static { height: auto; }
    .status { dock: bottom; height: 1; color: $text-muted; }
    """

    TITLE = "Selfu"
    SUB_TITLE = "system self-check"

    BINDINGS = [
        Binding("r", "refresh_active", "Refresh tab"),
        Binding("ctrl+r", "refresh_all", "Refresh all"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("Net", id="network"):
                yield Static(id="network-content")
            with TabPane("CPU", id="cpu"):
                yield Static(id="cpu-content")
            with TabPane("Disk", id="disk"):
                yield Static(id="disk-content")
            with TabPane("Mem", id="memory"):
                yield Static(id="memory-content")
            with TabPane("Sys", id="system"):
                yield Static(id="system-content")
            with TabPane("Health", id="health"):
                yield Static(id="health-content")
            with TabPane("Sec", id="security"):
                yield Static(id="security-content")
            with TabPane("Updates", id="updates"):
                yield Static(id="updates-content")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_all()

    def _set(self, widget_id: str, renderable) -> None:
        try:
            self.query_one(f"#{widget_id}", Static).update(renderable)
        except Exception as exc:  # noqa: BLE001
            self.query_one(f"#{widget_id}", Static).update(f"[b red]Error:[/] {exc}")

    def refresh_network(self) -> None:
        self._set("network-content", ui.render_network(net_checks.check_all()))

    def refresh_cpu(self) -> None:
        self._set("cpu-content", ui.render_cpu(cpu_checks.check_cpu()))

    def refresh_disk(self) -> None:
        self._set("disk-content", ui.render_disk(disk_checks.check_disk()))

    def refresh_memory(self) -> None:
        self._set("memory-content", ui.render_memory(mem_checks.check_memory()))

    def refresh_system(self) -> None:
        from rich.console import Group

        info = sys_checks.check_all()
        renderable = Group(
            ui.render_shell_config(info.shell),
            ui.render_systemd(info.systemd),
            ui.render_host(info.host),
        )
        self._set("system-content", renderable)

    def refresh_health(self) -> None:
        self._set("health-content", ui.render_health(health_checks.check_all()))

    def refresh_security(self) -> None:
        self._set("security-content", ui.render_security(sec_checks.check_all()))

    def refresh_updates(self) -> None:
        self._set("updates-content", ui.render_updates(upd_checks.check_updates()))

    def refresh_all(self) -> None:
        self.refresh_network()
        self.refresh_cpu()
        self.refresh_disk()
        self.refresh_memory()
        self.refresh_system()
        self.refresh_health()
        self.refresh_security()
        self.refresh_updates()

    def action_refresh_active(self) -> None:
        tabs = self.query_one(TabbedContent)
        active = tabs.active
        handler = {
            "network": self.refresh_network,
            "cpu": self.refresh_cpu,
            "disk": self.refresh_disk,
            "memory": self.refresh_memory,
            "system": self.refresh_system,
            "health": self.refresh_health,
            "security": self.refresh_security,
            "updates": self.refresh_updates,
        }.get(active)
        if handler:
            handler()

    def action_refresh_all(self) -> None:
        self.refresh_all()
