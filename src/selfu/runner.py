"""Subprocess wrapper for invoking native system commands.

All checks delegate to system-native utilities (df, free, nmcli, resolvectl,
firewall-cmd, systemctl, ...) instead of relying on third-party tools. This
module centralises error handling so check functions stay readable.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Sequence


class CommandError(RuntimeError):
    """Raised when a native command is missing or returns a non-zero code."""


@dataclass(frozen=True)
class CommandResult:
    cmd: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        return self.stdout.strip()


def which(binary: str) -> str | None:
    return shutil.which(binary)


def run(cmd: Sequence[str], *, timeout: int = 10, check: bool = False) -> CommandResult:
    """Run a native command and capture its output.

    ``check=True`` raises :class:`CommandError` on non-zero exit. Missing
    binaries raise immediately so callers can present a friendly message.
    """
    if not cmd:
        raise CommandError("empty command")
    binary = cmd[0]
    if shutil.which(binary) is None:
        raise CommandError(f"command not found: {binary}")

    try:
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"timed out after {timeout}s: {' '.join(cmd)}") from exc

    result = CommandResult(
        cmd=tuple(cmd),
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
    if check and not result.ok:
        raise CommandError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n{result.stderr.strip()}"
        )
    return result


def run_optional(cmd: Sequence[str], *, timeout: int = 10) -> CommandResult | None:
    """Like :func:`run` but returns ``None`` when the binary is unavailable."""
    if not cmd or shutil.which(cmd[0]) is None:
        return None
    try:
        return run(cmd, timeout=timeout)
    except CommandError:
        return None
