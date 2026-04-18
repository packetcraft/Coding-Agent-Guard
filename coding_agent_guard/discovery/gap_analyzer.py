"""Cross-reference repos × agents → COVERED / SHADOW_HOOK / UNGUARDED."""
from __future__ import annotations

from coding_agent_guard.discovery import GapResult, RepoConfig


def analyze(repo_configs: list[RepoConfig]) -> list[GapResult]:
    """
    For each RepoConfig, determine whether the repo is:
      - COVERED:      at least one hook that resolves to a known guard
      - SHADOW_HOOK:  hooks exist but none are a known guard
      - UNGUARDED:    no hooks registered at all
    """
    results: list[GapResult] = []

    for rc in repo_configs:
        hooks = rc.hook_entries
        guard_hooks = [h for h in hooks if h.is_guard]
        non_guard_hooks = [h for h in hooks if not h.is_guard]

        if guard_hooks:
            status = "COVERED"
            hook_command = guard_hooks[0].command
        elif non_guard_hooks:
            status = "SHADOW_HOOK"
            hook_command = non_guard_hooks[0].command
        elif rc.artifact_files and "Artifacts" in rc.agent:
            # Special case: Antigravity (Artifacts) has no native hooks
            # but is being passively monitored via artifacts.
            status = "ARTIFACT_ONLY"
            hook_command = None
        elif rc.external_brain_session:
            # New case: Detected via external brain mapping
            status = "EXTERNAL_BRAIN"
            hook_command = None
        else:
            status = "UNGUARDED"
            hook_command = None

        results.append(GapResult(
            repo_path=rc.repo_path,
            agent=rc.agent,
            status=status,
            hook_command=hook_command,
            inherited=rc.inherited_from is not None,
            config_path=rc.config_path,
            artifact_files=rc.artifact_files,
            external_brain_session=rc.external_brain_session
        ))


    return results
