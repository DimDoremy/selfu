"""Shell-completion generation and installation for the ``selfu`` CLI."""

from __future__ import annotations

import os
from pathlib import Path

SUPPORTED: tuple[str, ...] = ("bash", "zsh", "fish", "powershell", "pwsh")

# complete_var mirrors the convention used by typer/click for this program.
COMPLETE_VAR = "_SELFU_COMPLETE"
PROG_NAME = "selfu"


def generate(shell: str) -> str:
    """Return the completion script for *shell* (raises ValueError if unsupported)."""
    import typer.completion as tc

    if shell not in SUPPORTED:
        raise ValueError(f"unsupported shell {shell!r}; choose from {', '.join(SUPPORTED)}")
    return tc.get_completion_script(prog_name=PROG_NAME, complete_var=COMPLETE_VAR, shell=shell)


def _install_target(shell: str) -> Path | None:
    """Conventional, user-writable install path per shell (None if not file-installable)."""
    home = Path.home()
    xdg = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    if shell == "bash":
        return xdg / "bash-completion" / "completions" / PROG_NAME
    if shell == "zsh":
        # zsh site-functions dir is auto-loaded when on fpath; ~/.zfunc is the
        # widely-documented user dir that users add to fpath once.
        return home / ".zfunc" / f"_{PROG_NAME}"
    if shell == "fish":
        return home / ".config" / "fish" / "completions" / f"{PROG_NAME}.fish"
    # powershell/pwsh need a line in $PROFILE, not a standalone file.
    return None


def install(shell: str) -> Path:
    """Write the completion script to the shell's standard location.

    Returns the written path. Raises ValueError for shells that cannot be
    installed as a plain file (powershell/pwsh) - call :func:`hint` for those.
    """
    target = _install_target(shell)
    if target is None:
        raise ValueError(f"{shell!r} completion must be added to $PROFILE; use generate() + hint()")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generate(shell))
    return target


def hint(shell: str, path: Path | None = None) -> str:
    """Post-install guidance the user still needs to act on."""
    if shell == "bash":
        loaded = "auto-loaded by bash-completion" if path else "reload your shell"
        return f"Restart your shell or run: exec bash  ({loaded})."
    if shell == "zsh":
        line = "fpath+=('~/.zfunc')\nautoload -Uz compinit && compinit"
        return f"Ensure ~/.zfunc is on fpath; add to ~/.zshrc:\n  {line}"
    if shell == "fish":
        return "Auto-loaded by fish on next shell start - nothing else to do."
    if shell in ("powershell", "pwsh"):
        return "Add to your PowerShell $PROFILE:\n  " + generate(shell).strip().replace("\n", "\n  ")
    return ""
