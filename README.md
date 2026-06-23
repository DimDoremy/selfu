# selfu

A sysadmin self-check toolkit built with [typer](https://typer.tiangolo.com/),
[rich](https://rich.readthedocs.io/) and [textual](https://textual.textualize.io/).

`selfu` inspects the host using **native system commands** (`df`, `free`,
`resolvectl`, `nmcli`, `firewall-cmd`, `systemctl`, `hostnamectl`, ...) rather
than extra Python dependencies, so it runs anywhere those tools exist.

## Install

```bash
uv pip install -e .     # or: pip install -e .
```

This registers the `selfu` console script (and keeps `python main.py` working).

## Usage

```text
selfu                          # top-level help
selfu network                  # all network checks at once
selfu network dns              # DNS servers (resolvectl / /etc/resolv.conf)
selfu network resolve [domain] # actually resolve a domain (getent/resolvectl)
selfu network connectivity     # ping a host (default: 1.1.1.1)
selfu network connectivity -H example.com
selfu network wifi             # Wi-Fi state + scan (nmcli)
selfu network firewall         # firewalld / nftables / iptables
selfu network ports            # listening sockets + conn summary (ss)
selfu cpu                      # load avg + top CPU/MEM processes
selfu disk                     # df -h with a use% bar
selfu disk -i                  # also show inode usage (df -i)
selfu disk --raw               # raw df output
selfu memory                   # free with a usage bar
selfu health                   # boot errors + OOM + boot time + NTP + entropy
selfu security                 # failed logins + sessions + MAC + SSH config
selfu updates                  # distro-detected: pending/security updates + reboot
selfu system                   # shell rc + systemd + host
selfu system shell             # rc/profile file inventory
selfu system systemd           # failed / enabled units
selfu system host              # hostnamectl identity
selfu all                      # consolidated plain-text report
selfu dashboard                # interactive Textual TUI
selfu completions bash         # print shell-completion script
selfu completions fish --install   # install it permanently
```

#### Shell completion

`selfu` ships completion for bash, zsh, fish and PowerShell. Either let typer
wire it in (`selfu --install-completion`) or use the dedicated command:

```bash
eval "$(selfu completions bash)"        # current session only
selfu completions zsh --install         # write to ~/.zfunc/_selfu
selfu completions fish --install        # write to ~/.config/fish/completions/
```

`selfu updates` detects the distro family from `/etc/os-release` and dispatches
to the right backend: `dnf`/`yum` (RHEL family), `apt` (Debian family),
`checkupdates` (Arch family), `zypper` (SUSE family). Reboot detection uses
`/var/run/reboot-required` (Debian), `needs-restarting -r` (RHEL) or running
vs. installed kernel comparison as a last resort.

### Textual dashboard

`selfu dashboard` opens a tabbed interface (Network / Disk / Memory / System):

| Key       | Action                |
|-----------|-----------------------|
| `r`       | Refresh active tab    |
| `Ctrl+R`  | Refresh everything    |
| `q`       | Quit                  |

## Project layout

```
src/selfu/
├── cli.py            # typer command tree
├── completions.py    # shell-completion generation & install
├── runner.py         # subprocess wrapper for native commands
├── ui.py             # rich panels/tables for every check
├── tui.py            # textual dashboard
└── checks/
    ├── network.py    # dns / resolve / connectivity / wifi / firewall / ports
    ├── cpu.py        # load average + top processes
    ├── disk.py       # df (+ inode usage)
    ├── memory.py     # free
    ├── health.py     # journal errors / OOM / boot time / NTP / entropy
    ├── security.py   # failed logins / sessions / MAC / SSH config
    ├── system.py     # shell rc/profile / systemd (+immutable path resolution) / hostnamectl
    └── updates.py    # distro-detected pending/security updates + reboot
```

#### Immutable-system awareness

`selfu system systemd` detects ostree/image-based hosts and, for each failed
unit, resolves its `FragmentPath`. Units shipped in the read-only
`/usr/lib/systemd/system/` tree are flagged as non-editable with a
`systemctl edit <unit>` drop-in hint, while `/etc/systemd/system/` units are
shown as directly editable.

Each check returns a typed dataclass, so the rendering layer (`ui.py`,
`tui.py`) and the data-gathering layer stay cleanly separated.
