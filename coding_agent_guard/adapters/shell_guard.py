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
from coding_agent_guard.core.telemetry import utcnow, write_audit

def main():
    # If no arguments, just start an interactive shell
    shell_to_run = os.environ.get("COMSPEC", "cmd.exe") if sys.platform == "win32" else os.environ.get("SHELL", "/bin/bash")
    
    # Check if we are being called as a command wrapper (e.g. `shell_guard -c "rm -rf /"`)
    # Or just passthrough all args to the real shell
    args = sys.argv[1:]
    
    session_id = os.environ.get("GUARD_SESSION_ID", str(uuid.uuid4()))
    cfg = Config()
    audit_path = (Path.cwd() / cfg.audit_path).resolve()

    def log_command(cmd_list: list[str]):
        record = {
            "schema_version": "v1",
            "event_type": "SHELL_COMMAND",
            "timestamp": utcnow(),
            "session_id": session_id,
            "agent": "Shell-Guard",
            "data": {
                "command": " ".join(cmd_list),
                "cwd": os.getcwd()
            }
        }
        write_audit(
            audit_path=audit_path,
            session_id=session_id,
            record=record,
            is_new_session=False,
            hook_model=cfg.guard_model,
            timeout_ms=cfg.timeout_ms,
            agent_name="Shell-Guard"
        )

    if args:
        log_command(args)
        # Execute the command
        res = subprocess.run(args, shell=True)
        sys.exit(res.returncode)
    else:
        # Interactive mode or no-args call
        # In a real implementation, we might want to wrap the interactive session,
        # but for an audit shim, capturing the `-c` calls from agents is the priority.
        subprocess.run([shell_to_run])

if __name__ == "__main__":
    main()
