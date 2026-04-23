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
from coding_agent_guard.core.guard import GuardEngine

def main():
    if len(sys.argv) < 2:
        print("Usage: python mcp_shim.py <real_mcp_command> [args...]")
        sys.exit(1)

    real_command = sys.argv[1:]
    
    session_id = os.environ.get("GUARD_SESSION_ID", str(uuid.uuid4()))
    cfg = Config()
    engine = GuardEngine(cfg)
    
    import subprocess
    import threading

    proc = subprocess.Popen(
        real_command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        bufsize=0,
        text=True
    )
    
    def proxy_in():
        for line in sys.stdin:
            try:
                msg = json.loads(line)
                if msg.get("method") == "tools/call":
                    params = msg.get("params") or {}
                    tool_name = params.get("name", "unknown")
                    tool_input = params.get("arguments", {})
                    
                    # ── Call Guard Engine ──────────────────────────────────
                    verdict, block_reason = engine.check_tool(
                        tool_name=f"mcp__{tool_name}", # Prefix for attribution
                        tool_input=tool_input,
                        agent_name="Antigravity",
                        session_id=session_id,
                        cwd=os.getcwd()
                    )
                    
                    if verdict == "BLOCK":
                        if cfg.audit_only:
                            sys.stderr.write(f"[coding-agent-guard] AUDIT: would have blocked MCP tool '{tool_name}': {block_reason}\n")
                        else:
                            sys.stderr.write(f"[coding-agent-guard] BLOCK: MCP tool '{tool_name}' blocked: {block_reason}\n")
                            # Return JSON-RPC Error response
                            err_resp = {
                                "jsonrpc": "2.0",
                                "id": msg.get("id"),
                                "error": {
                                    "code": -32000,
                                    "message": f"Guard Block: {block_reason}"
                                }
                            }
                            sys.stdout.write(json.dumps(err_resp) + "\n")
                            sys.stdout.flush()
                            continue # Don't forward to real server

            except Exception as e:
                sys.stderr.write(f"[coding-agent-guard] MCP Shim Error: {e}\n")
            
            proc.stdin.write(line)
            proc.stdin.flush()

    def proxy_out():
        for line in proc.stdout:
            # Audit responses if needed (PostToolUse)
            # For now, we mainly focus on blocking the request (PreToolUse)
            sys.stdout.write(line)
            sys.stdout.flush()

    t_in = threading.Thread(target=proxy_in, daemon=True)
    t_out = threading.Thread(target=proxy_out, daemon=True)
    
    t_in.start()
    t_out.start()
    
    proc.wait()

if __name__ == "__main__":
    main()
