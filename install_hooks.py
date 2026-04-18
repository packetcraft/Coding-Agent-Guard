import json
import sys
from pathlib import Path


def _load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _merge_hook_list(existing: list, new_entries: list, guard_cmd: str) -> tuple[list, int, int]:
    """Merge new hook entries into an existing list.

    Deduplicates by (matcher, command). Returns (merged_list, added, skipped).
    """
    merged = list(existing)
    added = skipped = 0
    for entry in new_entries:
        matcher = entry.get("matcher")
        # Check if this matcher already has our command wired up
        already_present = any(
            e.get("matcher") == matcher and any(
                h.get("command") == guard_cmd for h in e.get("hooks", [])
            )
            for e in merged
        )
        if already_present:
            skipped += 1
        else:
            merged.append(entry)
            added += 1
    return merged, added, skipped


def install_hooks(target_dir: str, force: bool = False) -> None:
    target_path = Path(target_dir).resolve()
    if not target_path.is_dir():
        print(f"Error: {target_dir} is not a directory.")
        return

    # Path to this project's guard executable
    guard_exe = Path(__file__).parent / "venv" / "Scripts" / "coding-agent-guard.exe"
    if not guard_exe.exists():
        guard_cmd = "coding-agent-guard"
    else:
        guard_cmd = str(guard_exe).replace("\\", "/")

    # ── Claude Settings ───────────────────────────────────────────────────────
    claude_dir = target_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    claude_settings_path = claude_dir / "settings.json"

    new_claude_hooks = {
        "PreToolUse": [
            {"matcher": m, "hooks": [{"type": "command", "command": guard_cmd}]}
            for m in ["Bash", "Edit", "Write", "WebFetch", "mcp__*"]
        ],
        "PostToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": guard_cmd}]}
        ],
    }

    if force or not claude_settings_path.exists():
        claude_out = {"hooks": new_claude_hooks}
        action = "Installed"
    else:
        existing = _load_json(claude_settings_path)
        existing_hooks = existing.get("hooks", {})
        merged_hooks = {}
        total_added = total_skipped = 0
        for event, entries in new_claude_hooks.items():
            merged, added, skipped = _merge_hook_list(
                existing_hooks.get(event, []), entries, guard_cmd
            )
            merged_hooks[event] = merged
            total_added += added
            total_skipped += skipped
        # Preserve any hook events we don't manage
        for event, entries in existing_hooks.items():
            if event not in merged_hooks:
                merged_hooks[event] = entries
        claude_out = {**existing, "hooks": merged_hooks}
        action = f"Updated (added {total_added}, skipped {total_skipped} already-present)"

    with open(claude_settings_path, "w", encoding="utf-8") as f:
        json.dump(claude_out, f, indent=2)
    print(f"[Claude] {action}: {claude_settings_path}")

    # ── Gemini Settings ───────────────────────────────────────────────────────
    gemini_dir = target_path / ".gemini"
    gemini_dir.mkdir(exist_ok=True)
    gemini_settings_path = gemini_dir / "settings.json"

    new_gemini_hooks = {
        "BeforeTool": [
            {"matcher": ".*", "hooks": [{"name": "coding-agent-guard", "type": "command", "command": guard_cmd}]}
        ],
        "AfterTool": [
            {"matcher": ".*", "hooks": [{"name": "coding-agent-guard", "type": "command", "command": guard_cmd}]}
        ],
    }

    if force or not gemini_settings_path.exists():
        gemini_out = {"hooks": new_gemini_hooks}
        action = "Installed"
    else:
        existing = _load_json(gemini_settings_path)
        existing_hooks = existing.get("hooks", {})
        merged_hooks = {}
        total_added = total_skipped = 0
        for event, entries in new_gemini_hooks.items():
            merged, added, skipped = _merge_hook_list(
                existing_hooks.get(event, []), entries, guard_cmd
            )
            merged_hooks[event] = merged
            total_added += added
            total_skipped += skipped
        for event, entries in existing_hooks.items():
            if event not in merged_hooks:
                merged_hooks[event] = entries
        gemini_out = {**existing, "hooks": merged_hooks}
        action = f"Updated (added {total_added}, skipped {total_skipped} already-present)"

    with open(gemini_settings_path, "w", encoding="utf-8") as f:
        json.dump(gemini_out, f, indent=2)
    print(f"[Gemini] {action}: {gemini_settings_path}")


def wrap_mcp(target_config: str, force: bool = False) -> None:
    config_path = Path(target_config).resolve()
    if not config_path.exists():
        print(f"Error: {target_config} does not exist.")
        return

    data = _load_json(config_path)
    mcp_servers = data.get("mcpServers", {})
    if not mcp_servers:
        print(f"No mcpServers found in {target_config}")
        return

    # Path to the shim
    shim_py = Path(__file__).parent / "coding_agent_guard" / "adapters" / "mcp_shim.py"
    # Use the venv python to ensure dependencies are available
    venv_py = Path(__file__).parent / "venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        venv_py = Path(sys.executable)
    
    shim_cmd = f"{venv_py} {shim_py}".replace("\\", "/")

    wrapped_count = 0
    for name, entry in mcp_servers.items():
        cmd = entry.get("command")
        if not cmd:
            continue
        
        # Don't double-wrap
        if isinstance(cmd, list):
            cmd_str = " ".join(str(c) for c in cmd)
        else:
            cmd_str = str(cmd)
            
        if "mcp_shim.py" in cmd_str:
            continue
            
        # Wrap the command
        args = entry.get("args", [])
        original_full = [cmd] + args if isinstance(cmd, str) else cmd + args
        
        entry["command"] = str(venv_py).replace("\\", "/")
        entry["args"] = [str(shim_py).replace("\\", "/")] + [str(c) for c in original_full]
        wrapped_count += 1

    if wrapped_count > 0:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[MCP] Wrapped {wrapped_count} servers in {target_config}")
    else:
        print(f"[MCP] No servers newly wrapped in {target_config}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    mcp_mode = "--mcp" in sys.argv

    if not args:
        print("Usage:")
        print("  python install_hooks.py <target_directory> [--force]        # Install repo hooks")
        print("  python install_hooks.py --mcp <config_file> [--force]      # Wrap MCP servers in config")
        print("\nOptions:")
        print("  --force  Overwrite existing settings / re-wrap already wrapped items")
    elif mcp_mode:
        wrap_mcp(args[0], force=force)
    else:
        install_hooks(args[0], force=force)
