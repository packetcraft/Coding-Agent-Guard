"""Universal Shell Guard: intercepts and logs shell commands for any agent.
Used for AUDIT-only logging when native hooks are unavailable.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
import subprocess
from pathlib import Path

from coding_agent_guard.core.config import Config
from coding_agent_guard.core.guard import GuardEngine

def main():
    # If no arguments, just start an interactive shell
    shell_to_run = os.environ.get("COMSPEC", "cmd.exe") if sys.platform == "win32" else os.environ.get("SHELL", "/bin/bash")
    
    args = sys.argv[1:]
    
    session_id = os.environ.get("GUARD_SESSION_ID", str(uuid.uuid4()))
    cfg = Config()
    engine = GuardEngine(cfg)

    def check_and_run(cmd_list: list[str]):
        # 1. Run through GuardEngine
        tool_input = {"command": " ".join(cmd_list)}
        verdict, block_reason = engine.check_tool(
            tool_name="bash",
            tool_input=tool_input,
            agent_name="Antigravity",
            session_id=session_id,
            cwd=os.getcwd()
        )

        if verdict == "BLOCK":
            if cfg.audit_only:
                sys.stderr.write(f"[coding-agent-guard] AUDIT: would have blocked shell command: {block_reason}\n")
            else:
                sys.stderr.write(f"[coding-agent-guard] BLOCK: shell command blocked: {block_reason}\n")
                sys.exit(1)

        # 2. Execute the command
        res = subprocess.run(cmd_list, shell=True)
        sys.exit(res.returncode)

    if args:
        check_and_run(args)
    else:
        # Interactive mode or no-args call
        subprocess.run([shell_to_run])

if __name__ == "__main__":
    main()
