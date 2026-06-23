"""Network checks using native tools (resolvectl, nmcli, ping, firewall-cmd)."""

from __future__ import annotations

from dataclasses import dataclass, field


def _split_servers(value: str) -> list[str]:
    """Split a resolvectl DNS server field on whitespace and commas."""
    import re

    return [part for part in re.split(r"[\s,]+", value.strip()) if part]


@dataclass
class DnsInfo:
    servers: list[str] = field(default_factory=list)
    domain: str = ""
    raw: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.servers)


@dataclass
class ConnectivityInfo:
    target: str
    reachable: bool
    detail: str = ""


@dataclass
class WifiNetwork:
    ssid: str
    signal: int
    security: str
    connected: bool


@dataclass
class WifiInfo:
    enabled: bool
    connected_ssid: str = ""
    networks: list[WifiNetwork] = field(default_factory=list)
    raw: str = ""

    @property
    def ok(self) -> bool:
        return self.enabled and bool(self.connected_ssid)


@dataclass
class FirewallInfo:
    backend: str
    running: bool
    zones: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class ListeningSocket:
    proto: str          # tcp / udp
    address: str        # local address:port
    port: int
    process: str        # "name pid=1234" or "-"
    bind: str           # 0.0.0.0 / :: / 127.0.0.1 ...


@dataclass
class PortsInfo:
    listening: list[ListeningSocket] = field(default_factory=list)
    established: int = 0
    time_wait: int = 0
    raw: str = ""

    @property
    def public_listeners(self) -> list[ListeningSocket]:
        return [s for s in self.listening if s.bind not in ("127.0.0.1", "::1", "localhost")]


@dataclass
class ResolveInfo:
    domain: str
    resolved: bool
    addresses: list[str] = field(default_factory=list)
    detail: str = ""


def check_dns() -> DnsInfo:
    """Inspect DNS configuration via ``resolvectl`` (falls back to /etc/resolv.conf)."""
    from ..runner import run, run_optional, CommandError

    info = DnsInfo()
    result = run_optional(["resolvectl", "status"])
    if result is not None:
        info.raw = result.stdout.strip()
        current: list[str] = []
        all_servers: list[str] = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            low = stripped.lower()
            if low.startswith("current dns server:"):
                value = stripped.split(":", 1)[1]
                current.extend(_split_servers(value))
            elif low.startswith("dns servers:"):
                value = stripped.split(":", 1)[1]
                all_servers.extend(_split_servers(value))
            elif low.startswith("dnsdomain:") or low.startswith("default domain:"):
                info.domain = stripped.split(":", 1)[1].strip()
        # Current DNS server first, then the rest, preserving order, de-duplicated.
        seen: set[str] = set()
        for server in current + all_servers:
            if server and server not in seen:
                seen.add(server)
                info.servers.append(server)
        return info

    # No resolvectl available - fall back to reading /etc/resolv.conf directly.
    try:
        from pathlib import Path

        text = Path("/etc/resolv.conf").read_text()
        info.raw = text.strip()
        for line in text.splitlines():
            line = line.strip()
            if line.lower().startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    info.servers.append(parts[1])
    except OSError:
        pass
    return info


def check_connectivity(host: str = "1.1.1.1") -> ConnectivityInfo:
    """Ping a host to verify basic connectivity."""
    from ..runner import run, run_optional

    ping = run_optional(["ping", "-c", "3", "-W", "2", host])
    if ping is not None:
        return ConnectivityInfo(
            target=host,
            reachable=ping.ok,
            detail=ping.stdout.strip().splitlines()[-1] if ping.stdout else ping.stderr.strip(),
        )

    getent = run_optional(["getent", "hosts", "example.com"])
    if getent is not None:
        return ConnectivityInfo(
            target="example.com",
            reachable=getent.ok and bool(getent.stdout.strip()),
            detail=getent.stdout.strip(),
        )
    return ConnectivityInfo(target=host, reachable=False, detail="no connectivity probe available")


def check_wifi() -> WifiInfo:
    """Use ``nmcli`` to enumerate wifi state."""
    from ..runner import run, run_optional

    info = WifiInfo(enabled=False)
    if run_optional(["nmcli", "radio", "wifi"]) is None:
        return info

    radio = run(["nmcli", "-t", "-f", "WIFI", "radio", "wifi"], timeout=5)
    info.enabled = radio.ok and radio.output.lower() == "enabled"

    dev = run(["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device", "status"], timeout=5)
    for line in dev.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0] == "wifi":
            if parts[1] in {"connected", "connected (externally)"}:
                info.connected_ssid = parts[2]
            break

    try:
        scan = run(["nmcli", "-t", "-f", "active,ssid,signal,security", "device", "wifi", "list"], timeout=15)
        for line in scan.stdout.splitlines():
            active, ssid, signal, security = (line.split(":") + ["", "", "", ""])[:4]
            if not ssid:
                continue
            try:
                signal_val = int(signal) if signal else 0
            except ValueError:
                signal_val = 0
            info.networks.append(
                WifiNetwork(
                    ssid=ssid,
                    signal=signal_val,
                    security=security or "open",
                    connected=active == "yes",
                )
            )
        info.networks.sort(key=lambda n: (not n.connected, -n.signal))
    except Exception:
        pass

    info.raw = "\n".join(filter(None, [radio.output, dev.output]))
    return info


def check_firewall() -> FirewallInfo:
    """Probe firewall state via firewalld, falling back to nft/iptables."""
    from ..runner import run, run_optional, CommandError

    # firewalld (default on Fedora/RHEL)
    fw = run_optional(["firewall-cmd", "--state"])
    if fw is not None:
        info = FirewallInfo(backend="firewalld", running=fw.ok and fw.output == "running")
        try:
            listing = run(["firewall-cmd", "--list-all"], timeout=5)
            info.raw = listing.stdout.strip()
            for line in listing.stdout.splitlines():
                stripped = line.strip()
                if stripped.startswith("services:"):
                    info.services = [s for s in stripped.split(":", 1)[1].split() if s]
                elif stripped.startswith("zones:"):
                    info.zones = [s for s in stripped.split(":", 1)[1].split() if s]
        except CommandError as exc:
            info.raw = str(exc)
        if not info.zones:
            zones = run_optional(["firewall-cmd", "--get-active-zones"])
            if zones is not None:
                for line in zones.stdout.splitlines():
                    name = line.strip().split()[0] if line.strip() and not line.startswith(" ") else None
                    if name and name not in info.zones:
                        info.zones.append(name)
        return info

    # nftables
    nft = run_optional(["nft", "list", "ruleset"])
    if nft is not None:
        return FirewallInfo(
            backend="nftables",
            running=bool(nft.stdout.strip()),
            raw=nft.stdout.strip(),
        )

    # iptables
    ipt = run_optional(["iptables", "-S"])
    if ipt is not None:
        return FirewallInfo(
            backend="iptables",
            running=bool(ipt.stdout.strip()),
            raw=ipt.stdout.strip(),
        )

    return FirewallInfo(backend="none", running=False, raw="no firewall tool found")


def check_ports() -> PortsInfo:
    """Use ``ss`` to enumerate listening sockets and connection-state summary."""
    from ..runner import run, run_optional

    info = PortsInfo()
    if run_optional(["ss", "--version"]) is None:
        return info

    listening = run(
        ["ss", "-tulpnH"],
        timeout=10,
    )
    info.raw = listening.stdout.strip()
    for line in listening.stdout.splitlines():
        parts = line.split(None, 6)
        if len(parts) < 5:
            continue
        proto, state = parts[0], parts[1]
        if state not in ("LISTEN", "UNCONN"):
            continue
        local = parts[4]
        process = parts[6] if len(parts) > 6 else "-"
        bind, port = _split_addr(local)
        if port == 0:
            continue
        info.listening.append(ListeningSocket(proto=proto, address=local, port=port, process=process, bind=bind))
    info.listening.sort(key=lambda s: (s.proto, s.port))

    summary = run_optional(["ss", "-s"])
    if summary is not None:
        for line in summary.stdout.splitlines():
            low = line.lower()
            if "estab" in low:
                digits = [int(t) for t in line.replace(",", " ").split() if t.lstrip("()").isdigit()]
                if digits:
                    info.established = digits[0]
            elif "time-wait" in low or "timewait" in low:
                digits = [int(t) for t in line.replace(",", " ").split() if t.lstrip("()").isdigit()]
                if digits:
                    info.time_wait = digits[0]
    return info


def _split_addr(local: str) -> tuple[str, int]:
    """Return (bind_addr, port) from an ss local-address field."""
    if not local:
        return "", 0
    if local.startswith("["):
        end = local.find("]")
        host = local[1:end]
        rest = local[end + 1 :]
    else:
        idx = local.rfind(":")
        if idx < 0:
            return local, 0
        host = local[:idx]
        rest = local[idx:]
    port_str = rest.rsplit(":", 1)[-1]
    try:
        port = int(port_str)
    except ValueError:
        port = 0
    return host or "*", port


def check_resolve(domain: str = "example.com") -> ResolveInfo:
    """Actually resolve a domain (not just list DNS servers)."""
    from ..runner import run, run_optional

    info = ResolveInfo(domain=domain, resolved=False)
    getent = run_optional(["getent", "hosts", domain])
    if getent is not None:
        info.detail = getent.stdout.strip() or getent.stderr.strip()
        for line in getent.stdout.splitlines():
            fields = line.split()
            if fields:
                info.addresses.append(fields[0])
        info.resolved = bool(info.addresses)
        return info

    query = run_optional(["resolvectl", "query", domain])
    if query is not None:
        info.detail = query.stdout.strip() or query.stderr.strip()
        for line in query.stdout.splitlines():
            fields = line.split(":")
            if fields and fields[0].strip():
                info.addresses.append(fields[0].strip())
        info.resolved = query.ok and bool(info.addresses)
        return info

    # No resolver tool - try ping as a last resort
    ping = run(["ping", "-c", "1", "-W", "2", domain], timeout=5)
    info.resolved = ping.ok
    info.detail = ping.output
    return info


def check_all() -> dict:
    return {
        "dns": check_dns(),
        "resolve": check_resolve(),
        "connectivity": check_connectivity(),
        "wifi": check_wifi(),
        "firewall": check_firewall(),
        "ports": check_ports(),
    }
