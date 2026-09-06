"""Run the repository's quality gates through one cross-platform entry point."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

COMMANDS: tuple[tuple[str, ...], ...] = (
    ("ruff", "check", "."),
    ("ruff", "format", "--check", "."),
    ("mypy", "src", "tests", "scripts"),
    ("pytest",),
)


def run(command: Sequence[str]) -> int:
    """Run one quality tool without invoking a platform-specific shell."""
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> int:
    """Run each quality gate and stop at the first failure."""
    for command in COMMANDS:
        return_code = run(command)
        if return_code != 0:
            return return_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
