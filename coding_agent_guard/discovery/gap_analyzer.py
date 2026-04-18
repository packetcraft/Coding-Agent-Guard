"""Cross-reference repos × agents → COVERED / BROKEN_HOOK / SHADOW_HOOK / UNGUARDED."""
from __future__ import annotations

import shutil
from pathlib import Path

from coding_agent_guard.discovery import GapResult, RepoConfig


def _check_hook_liveness(command: str) -> bool:
    """Return True if the first token of command resolves to an executable."""
    if not command:
        return False
    binary = command.split()[0]
    # Try as absolute/relative path first, then PATH lookup
    p = Path(binary)
    if p.is_absolute() or binary.startswith("."):
        return p.exists()
    return shutil.which(binary) is not None


def analyze(repo_configs: list[RepoConfig]) -> list[GapResult]:
    """
    For each RepoConfig, determine whether the repo is:
      - COVERED:      at least one hook that resolves to a known guard and is alive
      - BROKEN_HOOK:  guard hook registered but binary no longer exists
      - SHADOW_HOOK:  hooks exist but none are a known guard
      - ARTIFACT_ONLY: Antigravity detected via artifacts only (passive monitoring)
      - EXTERNAL_BRAIN: detected via external brain session
      - UNGUARDED:    no hooks registered at all
    """
    results: list[GapResult] = []

    for rc in repo_configs:
        hooks = rc.hook_entries
        guard_hooks = [h for h in hooks if h.is_guard]
        non_guard_hooks = [h for h in hooks if not h.is_guard]

        if guard_hooks:
            hook_command = guard_hooks[0].command
            healthy = _check_hook_liveness(hook_command)
            status = "COVERED" if healthy else "BROKEN_HOOK"
            hook_healthy: bool | None = healthy
        elif non_guard_hooks:
            status = "SHADOW_HOOK"
            hook_command = non_guard_hooks[0].command
            hook_healthy = None
        elif rc.artifact_files and "Artifacts" in rc.agent:
            status = "ARTIFACT_ONLY"
            hook_command = None
            hook_healthy = None
        elif rc.external_brain_session:
            status = "EXTERNAL_BRAIN"
            hook_command = None
            hook_healthy = None
        else:
            status = "UNGUARDED"
            hook_command = None
            hook_healthy = None

        results.append(GapResult(
            repo_path=rc.repo_path,
            agent=rc.agent,
            status=status,
            hook_command=hook_command,
            inherited=rc.inherited_from is not None,
            config_path=rc.config_path,
            artifact_files=rc.artifact_files,
            external_brain_session=rc.external_brain_session,
            hook_healthy=hook_healthy,
        ))

    return results
