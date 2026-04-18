"""Probe: detect installed AI coding agents."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from coding_agent_guard.discovery import AgentInfo


# VS Code extension directory (cross-platform)
def _vscode_extensions_dir() -> Path | None:
    if sys.platform == "win32":
        base = os.environ.get("USERPROFILE", "")
    else:
        base = os.environ.get("HOME", "")
    p = Path(base) / ".vscode" / "extensions"
    return p if p.is_dir() else None


def _run(*args: str) -> str:
    """Run a subprocess and return stdout, or '' on failure."""
    try:
        result = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _npm_global_version(package: str) -> str | None:
    """Return the installed version of an npm global package, or None."""
    out = _run("npm", "list", "-g", "--depth=0", "--json")
    if not out:
        return None
    try:
        data = json.loads(out)
        deps = data.get("dependencies", {})
        if package in deps:
            return deps[package].get("version")
    except json.JSONDecodeError:
        pass
    return None


def _pip_package_version(package: str) -> str | None:
    """Return the installed version of a pip package, or None."""
    out = _run(sys.executable, "-m", "pip", "show", package)
    for line in out.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return None


def _path_version(binary: str, version_flag: str = "--version") -> str | None:
    """Return version string from a PATH binary, or None if not found."""
    binary_path = shutil.which(binary)
    if not binary_path:
        return None
    out = _run(binary, version_flag)
    return out.split("\n")[0].strip() if out else "found"


def _vscode_extension_version(prefix: str) -> tuple[str | None, str | None]:
    """
    Search ~/.vscode/extensions for a directory matching prefix.
    Returns (version, path) or (None, None).
    """
    ext_dir = _vscode_extensions_dir()
    if ext_dir is None:
        return None, None
    for entry in sorted(ext_dir.iterdir()):
        if entry.is_dir() and entry.name.lower().startswith(prefix.lower()):
            # Extension dirs are named <publisher.name>-<version>
            parts = entry.name.rsplit("-", 1)
            version = parts[1] if len(parts) == 2 else None
            return version, str(entry)
    return None, None


def _app_installed_windows(name: str) -> str | None:
    """Check common Windows install locations for an app by name. Returns path or None."""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / name,
        Path(os.environ.get("PROGRAMFILES", "")) / name,
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / name,
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _app_installed_macos(bundle_name: str) -> str | None:
    """Check standard macOS /Applications for a .app bundle."""
    if sys.platform != "darwin":
        return None
    candidates = [
        Path("/Applications") / f"{bundle_name}.app",
        Path.home() / "Applications" / f"{bundle_name}.app",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _home_dir_exists(rel: str) -> str | None:
    if sys.platform == "win32":
        base = os.environ.get("USERPROFILE", "")
    else:
        base = os.environ.get("HOME", "")
    p = Path(base) / rel
    return str(p) if p.exists() else None


def _app_data_dir_exists(rel: str) -> str | None:
    """Check %APPDATA% (Roaming) or %LOCALAPPDATA% for a directory."""
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("APPDATA", "")) / rel,
            Path(os.environ.get("LOCALAPPDATA", "")) / rel,
        ]
        for c in candidates:
            if c.exists():
                return str(c)
    else:
        # Linux/macOS equivalents roughly
        base = Path.home() / ".config" / rel
        if base.exists():
            return str(base)
    return None


# ── Auth type detection ───────────────────────────────────────────────────────

def _claude_auth_type() -> str | None:
    """Detect how Claude Code is authenticated."""
    if sys.platform == "win32":
        base = os.environ.get("USERPROFILE", "")
    else:
        base = os.environ.get("HOME", "")
    credentials = Path(base) / ".claude" / ".credentials.json"
    if credentials.exists():
        try:
            data = json.loads(credentials.read_text(encoding="utf-8"))
            if data.get("claudeAiOauth"):
                return "OAuth"
        except Exception:
            pass
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "API key (env)"
    return None


def _gemini_auth_type() -> str | None:
    if os.environ.get("GEMINI_API_KEY"):
        return "API key (env)"
    if sys.platform == "win32":
        base = os.environ.get("USERPROFILE", "")
    else:
        base = os.environ.get("HOME", "")
    adc = Path(base) / ".config" / "gcloud" / "application_default_credentials.json"
    if adc.exists():
        return "gcloud ADC"
    # Antigravity often uses the same .gemini config surface
    gemini_cfg = Path(base) / ".gemini" / "settings.json"
    if gemini_cfg.exists():
        return "Configured (.gemini)"
    return None


# ── Main probe ────────────────────────────────────────────────────────────────

def detect_agents() -> list[AgentInfo]:
    """Probe all known agent installation surfaces and return discovered agents."""
    found: list[AgentInfo] = []

    # ── VS Code (Application) ─────────────────────────────────────────────────
    vscode_path = (
        shutil.which("code") or 
        _app_installed_windows("Microsoft VS Code") or 
        _app_installed_macos("Visual Studio Code")
    )
    if vscode_path:
        found.append(AgentInfo(
            name="VS Code",
            version=_path_version("code", "--version") if shutil.which("code") else None,
            install_path=vscode_path,
            install_method="app",
            auth_type=None,
        ))

    # ── Zed (Application) ─────────────────────────────────────────────────────
    zed_path = (
        shutil.which("zed") or 
        _app_installed_windows("Zed") or 
        _app_installed_macos("Zed") or 
        _app_data_dir_exists("Zed")
    )
    if zed_path:
        found.append(AgentInfo(
            name="Zed",
            version=None,
            install_path=zed_path,
            install_method="app",
            auth_type=None,
        ))

    # ── Antigravity (Application) ─────────────────────────────────────────────
    # Antigravity is Google's agentic IDE
    ag_path = (
        shutil.which("antigravity") or 
        _app_installed_windows("Antigravity") or 
        _app_installed_macos("Antigravity")
    )
    if ag_path:
        found.append(AgentInfo(
            name="Antigravity",
            version=None,
            install_path=ag_path,
            install_method="app",
            auth_type="Gemini / Google Auth",
        ))
    else:
        # Check for history only - do not flag as "active app" but still report for inventory
        brain_path = _home_dir_exists(".gemini/antigravity")
        if brain_path:
            found.append(AgentInfo(
                name="Antigravity (History)",
                version=None,
                install_path=brain_path,
                install_method="session_logs",
                auth_type=None,
            ))

    # ── Claude Code (npm global) ──────────────────────────────────────────────
    claude_npm = _npm_global_version("@anthropic-ai/claude-code")
    claude_path = shutil.which("claude")
    if claude_npm or claude_path:
        found.append(AgentInfo(
            name="Claude Code",
            version=claude_npm or _path_version("claude", "--version"),
            install_path=claude_path or "(npm global)",
            install_method="npm" if claude_npm else "path",
            auth_type=_claude_auth_type(),
        ))

    # ── Gemini CLI (npm global) ───────────────────────────────────────────────
    gemini_npm = _npm_global_version("@google/gemini-cli")
    gemini_path = shutil.which("gemini")
    if gemini_npm or gemini_path:
        found.append(AgentInfo(
            name="Gemini CLI",
            version=gemini_npm or _path_version("gemini", "--version"),
            install_path=gemini_path or "(npm global)",
            install_method="npm" if gemini_npm else "path",
            auth_type=_gemini_auth_type(),
        ))

    # ── Aider (pip) ───────────────────────────────────────────────────────────
    aider_ver = _pip_package_version("aider-chat")
    aider_path = shutil.which("aider")
    if aider_ver or aider_path:
        found.append(AgentInfo(
            name="Aider",
            version=aider_ver or _path_version("aider", "--version"),
            install_path=aider_path or "(pip)",
            install_method="pip" if aider_ver else "path",
            auth_type="API key (env)" if os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") else None,
        ))

    # ── GitHub Copilot (VS Code extension) ────────────────────────────────────
    copilot_ver, copilot_path = _vscode_extension_version("github.copilot-")
    if copilot_path:
        found.append(AgentInfo(
            name="GitHub Copilot",
            version=copilot_ver,
            install_path=copilot_path,
            install_method="vscode_extension",
            auth_type="OAuth (GitHub)",
        ))

    # ── Continue.dev (VS Code extension + home dir) ───────────────────────────
    continue_ver, continue_path = _vscode_extension_version("continue.continue-")
    continue_home = _home_dir_exists(".continue")
    if continue_path or continue_home:
        found.append(AgentInfo(
            name="Continue.dev",
            version=continue_ver,
            install_path=continue_path or continue_home or "",
            install_method="vscode_extension" if continue_path else "app",
            auth_type=None,
        ))

    # ── Amazon Q / CodeWhisperer (VS Code extension + home dir) ──────────────
    q_ver, q_path = _vscode_extension_version("amazonwebservices.amazon-q-vscode-")
    q_home = _home_dir_exists(".aws/amazonq")
    if q_path or q_home:
        found.append(AgentInfo(
            name="Amazon Q",
            version=q_ver,
            install_path=q_path or q_home or "",
            install_method="vscode_extension" if q_path else "app",
            auth_type="AWS credentials",
        ))

    # ── Cody (VS Code extension) ──────────────────────────────────────────────
    cody_ver, cody_path = _vscode_extension_version("sourcegraph.cody-ai-")
    if cody_path:
        found.append(AgentInfo(
            name="Cody (Sourcegraph)",
            version=cody_ver,
            install_path=cody_path,
            install_method="vscode_extension",
            auth_type=None,
        ))

    # ── Cursor (app / home dir) ───────────────────────────────────────────────
    cursor_path = (
        (_app_installed_windows("Cursor") if sys.platform == "win32" else None) or 
        _app_installed_macos("Cursor") or 
        _home_dir_exists(".cursor")
    )
    if cursor_path:
        found.append(AgentInfo(
            name="Cursor",
            version=None,
            install_path=cursor_path,
            install_method="app",
            auth_type=None,
        ))

    # ── Windsurf / Codeium (home dir) ────────────────────────────────────────
    codeium_home = _home_dir_exists(".codeium")
    if codeium_home:
        found.append(AgentInfo(
            name="Windsurf / Codeium",
            version=None,
            install_path=codeium_home,
            install_method="app",
            auth_type=None,
        ))

    # ── Claude Desktop (config file) ─────────────────────────────────────────
    if sys.platform == "win32":
        desktop_cfg = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        desktop_cfg = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        desktop_cfg = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    if desktop_cfg.exists():
        found.append(AgentInfo(
            name="Claude Desktop",
            version=None,
            install_path=str(desktop_cfg),
            install_method="app",
            auth_type=None,
        ))

    return found
