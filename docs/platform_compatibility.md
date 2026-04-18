# Platform Compatibility — Shadow AI Discovery

## Summary

The Shadow AI discovery code is fully compatible with **Windows**, **macOS**, and **Linux**. Every platform-specific path is handled via `sys.platform` guards; there are no hard-coded OS-only code paths that would cause a crash on another platform.

---

## Platform Branch Coverage

| Module | Windows | macOS | Linux |
|---|---|---|---|
| `agents.py` — VS Code extension dir | `USERPROFILE\.vscode\extensions` | `~/.vscode/extensions` | `~/.vscode/extensions` |
| `agents.py` — Claude Desktop config | `APPDATA\Claude\claude_desktop_config.json` | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` |
| `agents.py` — Cursor detection | `_app_installed_windows("Cursor")`, fallback `~/.cursor` | `~/.cursor` | `~/.cursor` |
| `agents.py` — home dir probes | `USERPROFILE` | `Path.home()` | `Path.home()` |
| `mcp_inventory.py` — Claude Desktop | `APPDATA\Claude\...` | `~/Library/Application Support/Claude/...` | `~/.config/Claude/...` |
| `config_crawler.py` — global config root | `USERPROFILE` | `Path.home()` | `Path.home()` |
| `scanner.py` — default scan root | `USERPROFILE\Documents\github` | `~/Documents/github` or `~/Documents/GitHub` | `~/projects`, `~/code`, `~/src` |
| `trust_analyzer.py` — home resolution | `USERPROFILE` | `Path.home()` | `Path.home()` |

---

## macOS — What Works

- **Claude Desktop** config is found at `~/Library/Application Support/Claude/claude_desktop_config.json` ✓
- **All home-dir agent probes** (`~/.cursor`, `~/.codeium`, `~/.claude`, `~/.gemini`, `~/.config/gcloud/`) ✓
- **VS Code extensions** at `~/.vscode/extensions` ✓
- **Default scan root** resolves to `~/Documents/github` or `~/Documents/GitHub` (whichever exists), then falls back to home ✓
- **MCP inventory** reads all five sources correctly using `Path.home()` ✓

---

## Known Gap — Cursor on macOS

On macOS, Cursor is typically installed as `/Applications/Cursor.app`. The current probe checks `~/.cursor` (home-dir config/data directory) and `_app_installed_macos("Cursor")` (`/Applications/Cursor.app`).

**Impact:** A fresh Cursor install that has never been opened may not populate `~/.cursor` yet, but the `/Applications/Cursor.app` probe will still detect it.  
**Workaround:** If neither probe fires, launch Cursor once so it creates `~/.cursor`, then re-run the scan.

---

## New Agent Coverage (v1.2.0)

The following agents were added in v1.2.0 with the platform-specific probe paths below:

| Agent | Windows | macOS | Linux |
|---|---|---|---|
| **Ollama** | `shutil.which("ollama")` or `~/.ollama/` | same | same |
| **LM Studio** | `%APPDATA%\LM-Studio\` or `%LOCALAPPDATA%\LM-Studio\` | `~/Library/Application Support/LM-Studio/` | `~/.config/LM-Studio/` |
| **Open Interpreter** | `pip show open-interpreter` + `shutil.which("interpreter")` | same | same |
| **GitHub Copilot CLI** | `shutil.which("gh")` + `gh extension list` | same | same |
| **CI/CD agents** | `.github/workflows/*.yml` scan under scan root | same | same |

CI/CD pipeline agent detection is filesystem-based and fully cross-platform — it walks `.github/workflows/*.yml` files regardless of OS.

---

## Linux Notes

- Claude Desktop uses `~/.config/Claude/claude_desktop_config.json` (XDG base dir convention).
- All other probes use `Path.home()` and are platform-agnostic.
- VS Code may be installed as a snap (`/snap/code/`) or flatpak — the extension directory probe relies on `~/.vscode/extensions` which both snap and native installs populate.
- LM Studio on Linux falls back to `~/.config/LM-Studio/` (the `_app_data_dir_exists` helper uses `~/.config/<rel>` on non-Windows).
