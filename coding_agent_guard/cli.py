"""Top-level CLI dispatcher for coding-agent-guard."""
from __future__ import annotations

import sys


def main() -> None:
    # Peek at the first argument before any parsing
    if len(sys.argv) > 1 and sys.argv[1] == "shadow-ai":
        # Strip the sub-command so argparse inside scanner.cli sees a clean argv
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from coding_agent_guard.discovery.scanner import cli
        cli()
    else:
        from coding_agent_guard.core.guard import main as guard_main
        guard_main()


if __name__ == "__main__":
    main()
