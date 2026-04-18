"""MCP Shim: intercepts JSON-RPC messages between an AI Agent and an MCP Server.
Used for AUDIT-only logging of IDE-based tool calls.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from coding_agent_guard.core.config import Config
from coding_agent_guard.core.telemetry import utcnow, write_audit

def main():
    if len(sys.argv) < 2:
        print("Usage: python mcp_shim.py <real_mcp_command> [args...]")
        sys.exit(1)

    real_command = sys.argv[1:]
    
    # Session ID is often not provided by the IDE, so we generate or use a persistent one
    session_id = os.environ.get("GUARD_SESSION_ID", str(uuid.uuid4()))
    
    cfg = Config()
    audit_path = (Path.cwd() / cfg.audit_path).resolve()
    
    # We'll use a subprocess to run the real server and pipe stdin/stdout
    import subprocess
    
    proc = subprocess.Popen(
        real_command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr, # pass through error stream
        bufsize=0,
        text=True
    )
    
    def log_event(event_type: str, data: dict):
        record = {
            "schema_version": "v1",
            "event_type": event_type,
            "timestamp": utcnow(),
            "session_id": session_id,
            "agent": "MCP-Shim",
            "data": data
        }
        write_audit(
            audit_path=audit_path,
            session_id=session_id,
            record=record,
            is_new_session=False, # We'll let the first write handle session start if needed
            hook_model=cfg.guard_model,
            timeout_ms=cfg.timeout_ms,
            agent_name="MCP-Shim"
        )

    # Simple loop to proxy stdin -> proc.stdin and proc.stdout -> stdout
    # Both directions are JSON-RPC messages separated by newlines or Content-Length
    # For simplicity, we assume one JSON-RPC message per line or valid block
    
    import threading

    def proxy_in():
        for line in sys.stdin:
            try:
                msg = json.loads(line)
                if msg.get("method") == "tools/call":
                    log_event("MCP_TOOL_CALL", {
                        "method": msg.get("method"),
                        "params": msg.get("params"),
                        "id": msg.get("id")
                    })
            except Exception:
                pass
            proc.stdin.write(line)
            proc.stdin.flush()

    def proxy_out():
        for line in proc.stdout:
            try:
                msg = json.loads(line)
                # Check if it's a response to a tool call
                if "result" in msg and "id" in msg:
                    log_event("MCP_TOOL_RESPONSE", {
                        "id": msg.get("id"),
                        "result": msg.get("result")
                    })
            except Exception:
                pass
            sys.stdout.write(line)
            sys.stdout.flush()

    t_in = threading.Thread(target=proxy_in, daemon=True)
    t_out = threading.Thread(target=proxy_out, daemon=True)
    
    t_in.start()
    t_out.start()
    
    proc.wait()

if __name__ == "__main__":
    main()
