import json
import os
import sys
from pathlib import Path

def install_hooks(target_dir):
    target_path = Path(target_dir).resolve()
    if not target_path.is_dir():
        print(f"Error: {target_dir} is not a directory.")
        return

    # Path to this project's guard executable
    guard_exe = Path(__file__).parent / "venv" / "Scripts" / "coding-agent-guard.exe"
    if not guard_exe.exists():
        # Fallback to just the command name if venv doesn't exist (e.g. global install)
        guard_cmd = "coding-agent-guard"
    else:
        guard_cmd = str(guard_exe).replace("\\", "/")

    # Claude Settings
    claude_dir = target_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    claude_settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": m, "hooks": [{"type": "command", "command": guard_cmd}]}
                for m in ["Bash", "Edit", "Write", "WebFetch", "mcp__*"]
            ],
            "PostToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": guard_cmd}]}
            ]
        }
    }
    with open(claude_dir / "settings.json", "w") as f:
        json.dump(claude_settings, f, indent=2)
    print(f"Installed Claude hooks to {claude_dir}")

    # Gemini Settings
    gemini_dir = target_path / ".gemini"
    gemini_dir.mkdir(exist_ok=True)
    gemini_settings = {
        "hooks": {
            "BeforeTool": [
                {"matcher": ".*", "hooks": [{"name": "coding-agent-guard", "type": "command", "command": guard_cmd}]}
            ],
            "AfterTool": [
                {"matcher": ".*", "hooks": [{"name": "coding-agent-guard", "type": "command", "command": guard_cmd}]}
            ]
        }
    }
    with open(gemini_dir / "settings.json", "w") as f:
        json.dump(gemini_settings, f, indent=2)
    print(f"Installed Gemini hooks to {gemini_dir}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python install_hooks.py <target_directory>")
    else:
        install_hooks(sys.argv[1])
