import glob
import json
import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st
import plotly.express as px

from coding_agent_guard.core.config import Config

# ── Verdict styling ───────────────────────────────────────────────────────────

_VERDICT_COLOUR = {
    "ALLOW":       "#9ECE6A",   # green
    "ALLOWLISTED": "#7AA2F7",   # blue
    "BLOCK":       "#F7768E",   # red
    "ERROR":       "#E0AF68",   # amber
}

_VERDICT_ICON = {
    "ALLOW":       "ALLOW",
    "ALLOWLISTED": "SKIP",
    "BLOCK":       "BLOCK",
    "ERROR":       "ERROR",
}

_METHOD_COLOUR = {
    "LLM":       "#BB9AF7",   # purple
    "REGEX":     "#FF9E64",   # orange
    "ALLOWLIST": "#7AA2F7",   # blue
    "PATH":      "#2AC3DE",   # teal
}


def _badge(verdict: str) -> str:
    colour = _VERDICT_COLOUR.get(verdict, "#888888")
    label  = _VERDICT_ICON.get(verdict, verdict)
    return f'<span style="background:{colour};color:#1a1b26;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700;">{label}</span>'


def _method_badge(method: str) -> str:
    colour = _METHOD_COLOUR.get(method, "#888888")
    return f'<span style="background:{colour};color:#1a1b26;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700;">{method}</span>'


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_audit(audit_path: str) -> tuple[pd.DataFrame, dict]:
    """Glob all session JSONL files and return (records_df, sessions_dict)."""
    pattern = str(Path(audit_path) / "*.jsonl")
    all_records: list[dict] = []
    sessions:    dict[str, dict] = {}

    for fpath in glob.glob(pattern):
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if rec.get("event_type") == "SESSION_START":
                        sessions[rec["session_id"]] = rec
                    elif rec.get("event_type") == "TOOL_CALL":
                        all_records.append(rec)
        except OSError:
            continue

    if not all_records:
        return pd.DataFrame(), sessions

    df = pd.DataFrame(all_records)
    _local_tz = datetime.datetime.now().astimezone().tzinfo
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.tz_convert(_local_tz)

    if "agent" not in df.columns:
        df["agent"] = "unknown"
    else:
        df["agent"] = df["agent"].fillna("unknown")

    df = df.sort_values("timestamp").reset_index(drop=True)
    return df, sessions


def _short_session(session_id: str) -> str:
    return session_id[:8] if session_id else "—"


def _tool_input_preview(row: pd.Series) -> str:
    ti = row.get("tool_input") or {}
    if isinstance(ti, str):
        return ti[:80]
    cmd = ti.get("command") or ti.get("url") or ti.get("file_path") or ""
    return str(cmd)[:80]


# ── Tab: Live Feed ────────────────────────────────────────────────────────────

def _render_live_feed(audit_path: str) -> None:
    st.caption("Auto-refreshes every 10 seconds. Shows the 50 most recent hook events across all sessions.")

    @st.fragment(run_every=10)
    def _feed() -> None:
        df, sessions = _load_audit(audit_path)

        if df.empty:
            st.info("No audit records found yet. Start a Claude Code or Gemini CLI session with hooks enabled.")
            return

        recent = df.tail(50).iloc[::-1].reset_index(drop=True)

        col_ts, col_agent, col_sess, col_tool, col_verdict, col_method, col_preview = st.columns([2, 1, 1, 1, 1, 1, 4])
        col_ts.markdown("**Timestamp**")
        col_agent.markdown("**Agent**")
        col_sess.markdown("**Session**")
        col_tool.markdown("**Tool**")
        col_verdict.markdown("**Verdict**")
        col_method.markdown("**Method**")
        col_preview.markdown("**Command / Input preview**")
        st.divider()

        for _, row in recent.iterrows():
            ts      = row["timestamp"].strftime("%H:%M:%S") if pd.notnull(row["timestamp"]) else "—"
            agent   = str(row.get("agent", "Claude"))
            sess    = _short_session(str(row.get("session_id", "")))
            tool    = str(row.get("tool_name", ""))
            verdict = str(row.get("verdict", ""))
            method  = str(row.get("inspection_method", "—")) if row.get("inspection_method") else "—"
            preview = _tool_input_preview(row)

            c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1, 1, 1, 1, 1, 4])
            c1.text(ts)
            c2.text(agent)
            c3.text(sess)
            c4.text(tool)
            c5.markdown(_badge(verdict), unsafe_allow_html=True)
            c6.markdown(_method_badge(method) if method != "—" else "—", unsafe_allow_html=True)
            c7.text(preview)

    _feed()


# ── Tab: Audit Explorer ───────────────────────────────────────────────────────

def _render_audit_explorer(audit_path: str) -> None:
    df, sessions = _load_audit(audit_path)

    if df.empty:
        st.info("No audit records found yet. Start a session with hooks enabled.")
        return

    # Sidebar filters
    with st.sidebar:
        st.markdown("### Audit Filters")
        
        # Agent selector
        agents = sorted(df["agent"].unique().tolist())
        selected_agents = st.multiselect("Agents", options=agents, default=[], placeholder="All agents")

        # Session selector
        session_ids = sorted(df["session_id"].unique().tolist())
        selected_sessions = st.multiselect("Sessions", options=session_ids, default=[], placeholder="All sessions")

        # Tool type
        tools = sorted(df["tool_name"].unique().tolist())
        selected_tools = st.multiselect("Tools", options=tools, default=[], placeholder="All tools")

        # Verdict
        verdicts = sorted(df["verdict"].unique().tolist())
        selected_verdicts = st.multiselect("Verdicts", options=verdicts, default=[], placeholder="All verdicts")

        keyword = st.text_input("Search tool input", key="ae_keyword", placeholder="e.g. rm -rf, curl, .env")
        st.divider()

    # Apply filters
    filtered = df.copy()
    if selected_agents:
        filtered = filtered[filtered["agent"].isin(selected_agents)]
    if selected_sessions:
        filtered = filtered[filtered["session_id"].isin(selected_sessions)]
    if selected_tools:
        filtered = filtered[filtered["tool_name"].isin(selected_tools)]
    if selected_verdicts:
        filtered = filtered[filtered["verdict"].isin(selected_verdicts)]
    if keyword:
        mask = filtered["tool_input"].astype(str).str.contains(keyword, case=False, na=False)
        filtered = filtered[mask]

    st.markdown(f"**{len(filtered):,} events** match filters")

    if filtered.empty:
        st.warning("No events match filters.")
        return

    # Paginated event table (newest first)
    PAGE_SIZE = 25
    filtered_desc = filtered.iloc[::-1].reset_index(drop=True)
    total_pages = max(1, (len(filtered_desc) - 1) // PAGE_SIZE + 1)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1, key="ae_page")
    page_df = filtered_desc.iloc[(page - 1) * PAGE_SIZE : page * PAGE_SIZE].reset_index(drop=True)

    # Header row
    h1, h2, h3, h4, h5, h6, h7, h8 = st.columns([2, 1, 1, 1, 1, 1, 1, 3])
    for col, label in zip([h1, h2, h3, h4, h5, h6, h7, h8], ["Timestamp", "Agent", "Session", "Hook", "Tool", "Verdict", "Method", "Input preview"]):
        col.markdown(f"**{label}**")
    st.divider()

    for i, (_, row) in enumerate(page_df.iterrows()):
        ts      = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(row["timestamp"]) else "—"
        agent   = str(row.get("agent", "Claude"))
        sess    = _short_session(str(row.get("session_id", "")))
        hook_ev = str(row.get("hook_event", "Pre"))[:3]
        tool    = str(row.get("tool_name", ""))
        verdict = str(row.get("verdict", ""))
        method  = str(row.get("inspection_method", "")) if row.get("inspection_method") else "—"
        preview = _tool_input_preview(row)

        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([2, 1, 1, 1, 1, 1, 1, 3])
        c1.text(ts)
        c2.text(agent)
        c3.text(sess)
        c4.text(hook_ev)
        c5.text(tool)
        c6.markdown(_badge(verdict), unsafe_allow_html=True)
        c7.markdown(_method_badge(method) if method != "—" else "—", unsafe_allow_html=True)
        c8.text(preview)

        with st.expander(f"Details — row {(page - 1) * PAGE_SIZE + i + 1}"):
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**Tool input (redacted)**")
                st.json(row.get("tool_input") or {})
            with d2:
                st.markdown("**Guard model verdict**")
                st.markdown(_badge(verdict), unsafe_allow_html=True)
                if row.get("block_reason"):
                    st.error(f"Block reason: {row['block_reason']}")
                if row.get("guard_raw_output"):
                    st.code(row["guard_raw_output"], language=None)
                st.markdown(f"**Model:** `{row.get('guard_model') or '—'}`")
                st.markdown(f"**Latency:** `{row.get('latency_ms', 0)} ms`")


# ── Tab: Dashboard ────────────────────────────────────────────────────────────

def _render_dashboard(audit_path: str) -> None:
    df, sessions = _load_audit(audit_path)

    if df.empty:
        st.info("No audit records yet.")
        return

    total       = len(df)
    blocks      = (df["verdict"] == "BLOCK").sum()
    errors      = (df["verdict"] == "ERROR").sum()
    block_rate  = blocks / total * 100 if total else 0
    session_cnt = df["session_id"].nunique()
    agent_cnt   = df["agent"].nunique() if "agent" in df.columns else 1
    avg_latency = df.loc[df["verdict"].isin(["ALLOW", "BLOCK"]), "latency_ms"].mean()

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total events",   f"{total:,}")
    k2.metric("Sessions",       f"{session_cnt:,}")
    k3.metric("Agents",         f"{agent_cnt:,}")
    k4.metric("Blocks",         f"{blocks:,}")
    k5.metric("Block rate",     f"{block_rate:.1f}%")
    k6.metric("Avg latency",    f"{avg_latency:.0f} ms" if not pd.isna(avg_latency) else "—")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**Verdict distribution**")
        verdict_counts = df["verdict"].value_counts().reset_index()
        verdict_counts.columns = ["Verdict", "Count"]
        fig = px.pie(verdict_counts, values="Count", names="Verdict", 
                     color="Verdict", color_discrete_map=_VERDICT_COLOUR)
        st.plotly_chart(fig, width="stretch")

    with col_right:
        st.markdown("**Events by tool type**")
        tool_counts = df["tool_name"].value_counts().head(10).reset_index()
        tool_counts.columns = ["Tool", "Count"]
        st.bar_chart(tool_counts.set_index("Tool"), width="stretch")


# ── Tab: Shadow AI ────────────────────────────────────────────────────────────

_SEV_COLOUR = {
    "HIGH":   "#F7768E",
    "MEDIUM": "#E0AF68",
    "LOW":    "#9ECE6A",
}

_STATUS_COLOUR = {
    "COVERED":     "#9ECE6A",
    "SHADOW_HOOK": "#E0AF68",
    "UNGUARDED":   "#F7768E",
}


def _sev_badge(severity: str) -> str:
    colour = _SEV_COLOUR.get(severity, "#888888")
    return f'<span style="background:{colour};color:#1a1b26;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700;">{severity}</span>'


def _status_badge(status: str) -> str:
    colour = _STATUS_COLOUR.get(status, "#888888")
    return f'<span style="background:{colour};color:#1a1b26;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700;">{status}</span>'


def _load_latest_shadow_scan(audit_path: str) -> Optional[dict]:
    scan_file = Path(audit_path) / "shadow_ai_scans.jsonl"
    if not scan_file.exists():
        return None
    last: Optional[dict] = None
    try:
        with open(scan_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        last = json.loads(line)
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return None
    return last


def _run_shadow_scan_now(audit_path: str, scan_root: Optional[str]) -> dict:
    from coding_agent_guard.discovery.scanner import run_scan, emit_audit
    from coding_agent_guard.discovery.report import as_json
    result = run_scan(scan_root=scan_root)
    emit_audit(result, Path(audit_path))
    return json.loads(as_json(result))


def _fmt_timestamp(ts_raw: str) -> str:
    """Format ISO timestamp to a human-readable string."""
    try:
        return (
            datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            .strftime("%Y-%m-%d %H:%M UTC")
        )
    except Exception:
        return ts_raw


def _hook_display_name(cmd: Optional[str]) -> str:
    """Extract just the binary name from a potentially long hook command path."""
    if not cmd:
        return "—"
    binary = cmd.split()[0]          # first token (ignore args)
    name = Path(binary).name         # basename of the path
    return name or binary


def _mcp_endpoint_display(server: dict) -> str:
    """For remote MCPs show the URL; for local show just the binary name."""
    url = server.get("url")
    if url:
        return str(url)
    cmd = server.get("command") or ""
    binary = Path(cmd.split()[0]).name if cmd else ""
    return binary or "—"


def _render_shadow_ai(audit_path: str) -> None:
    # ── Sidebar controls ──────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Shadow AI")
        scan_root_input = st.text_input(
            "Scan root",
            value="",
            placeholder="Auto-detect (leave blank)",
            key="shadow_scan_root",
        )
        scan_now = st.button("Scan Now", key="shadow_scan_now")
        st.divider()

    scan_root = scan_root_input.strip() or None

    # Run scan if requested
    if scan_now:
        with st.spinner("Running Shadow AI scan..."):
            scan = _run_shadow_scan_now(audit_path, scan_root)
        st.success(f"Scan complete — ID: {scan.get('scan_id', '?')}")
    else:
        scan = _load_latest_shadow_scan(audit_path)

    if scan is None:
        st.info(
            "No scan data found. Click **Scan Now** in the sidebar to run your first scan."
        )
        return

    summary = scan.get("summary", {})
    ts = _fmt_timestamp(scan.get("timestamp", "—"))

    st.caption(
        f"Last scan: **{ts}** \u2022 Root: `{scan.get('scan_root', '—')}` \u2022 "
        f"Scan ID: `{scan.get('scan_id', '—')}`"
    )

    # ── Metric row ────────────────────────────────────────────────────────────
    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Agents",       summary.get("agents_found", 0))
    m2.metric("Pairs",        summary.get("repo_agent_pairs", 0))   # repo × agent
    m3.metric("Covered",      summary.get("covered", 0))
    m4.metric("Unguarded",    summary.get("unguarded", 0))
    m5.metric("MCP Servers",  summary.get("mcp_servers", 0))
    m6.metric("High",         summary.get("high_findings", 0))
    m7.metric("Medium",       summary.get("medium_findings", 0))

    st.divider()

    # ── Findings ──────────────────────────────────────────────────────────────
    findings = scan.get("findings", [])
    _SEV_ORD = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    findings = sorted(findings, key=lambda f: _SEV_ORD.get(f.get("severity", ""), 9))

    st.markdown(f"#### Findings ({len(findings)})")
    if findings:
        for f in findings:
            sev = f.get("severity", "?")
            with st.expander(
                f"{sev}  \u2022  {f.get('id', '?')}  \u2014  {f.get('category', '')}",
                expanded=(sev == "HIGH"),
            ):
                c1, c2 = st.columns([1, 3])
                with c1:
                    st.markdown(_sev_badge(sev), unsafe_allow_html=True)
                    if f.get("agent"):
                        st.caption(f"Agent: {f['agent']}")
                with c2:
                    st.markdown(f.get("detail", ""))
                    st.caption(f"Source: `{f.get('source', '')}`")
                    st.info(f"**Fix:** {f.get('remediation', '')}")
    else:
        st.success("No findings — posture looks clean.")

    st.divider()

    # ── Coverage Map ──────────────────────────────────────────────────────────
    coverage = scan.get("coverage_map", [])
    unguarded_count = sum(1 for r in coverage if r.get("status") != "COVERED")

    st.markdown(f"#### Coverage Map ({len(coverage)} repo/agent pairs)")

    if coverage:
        _STATUS_ORD = {"UNGUARDED": 0, "SHADOW_HOOK": 1, "COVERED": 2}
        sorted_cov = sorted(
            coverage,
            key=lambda g: (
                _STATUS_ORD.get(g.get("status", ""), 9),
                g.get("agent", ""),
                g.get("repo_path", ""),
            ),
        )

        # Build compact dataframe: repo name only, hook binary name only
        rows = []
        for row in sorted_cov:
            repo_path = row.get("repo_path", "")
            repo_name = Path(repo_path).name or repo_path
            rows.append({
                "Status":    row.get("status", ""),
                "Agent":     row.get("agent", ""),
                "Repo":      repo_name,
                "Hook":      _hook_display_name(row.get("hook_command")),
                "Inherited": "yes" if row.get("inherited") else "no",
            })

        df_cov = pd.DataFrame(rows)

        if unguarded_count == 0:
            # Happy path: collapse the big table, surface a clear pass message
            st.success(
                f"All {len(sorted_cov)} repo/agent pairs are protected by Coding Agent Guard."
            )
            with st.expander("Show coverage details", expanded=False):
                st.dataframe(df_cov, use_container_width=True, hide_index=True)
        else:
            # Something is unguarded — show the full table so problems are visible
            st.dataframe(df_cov, use_container_width=True, hide_index=True)
    else:
        st.info("No coverage data.")

    st.divider()

    # ── Agent Inventory ───────────────────────────────────────────────────────
    agents = scan.get("agents", [])
    st.markdown(f"#### Agent Inventory ({len(agents)})")
    if agents:
        rows = []
        for a in agents:
            rows.append({
                "Name":    a.get("name", ""),
                "Version": a.get("version") or "—",
                "Method":  a.get("install_method", ""),
                "Auth":    a.get("auth_type") or "—",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No agents detected.")

    # ── MCP Surface ───────────────────────────────────────────────────────────
    mcps = scan.get("mcp_servers", [])
    st.markdown(f"#### MCP Surface ({len(mcps)} server(s))")
    if mcps:
        rows = []
        for s in mcps:
            trust = s.get("trust", False)
            rows.append({
                "Name":      s.get("name", ""),
                "Agent":     s.get("agent", ""),
                "Transport": s.get("transport", ""),
                "Trust":     "⚠ YES" if trust else "no",
                "Endpoint":  _mcp_endpoint_display(s),
                "Tools":     s.get("tool_count") if s.get("tool_count") is not None else "—",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No MCP servers configured.")


# ── How it Works ──────────────────────────────────────────────────────────────

def _render_how_it_works() -> None:
    st.markdown("## How Coding Agent Guard Works")

    st.markdown("""
Coding Agent Guard sits between your AI coding agent (Claude Code, Gemini CLI) and every tool
call it makes. It registers as a **pre-tool** and **post-tool** hook so it can inspect — and
optionally block — each action before and after it executes.
""")

    st.markdown("---")

    # ── Hook Interception ──
    st.markdown("### Hook Interception")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**PreToolUse (before execution)**")
        st.markdown("""
1. **Allowlist fast-path** — read-only shell commands (`git log`, `cat`, `ls`) are approved
   instantly without an LLM call. Shell composition (`|`, `>`, `&&`) is rejected to prevent bypass.
2. **Protected-path hard-block** — any write to the guard's own config or the agent's hook
   settings is blocked unconditionally, preventing the agent from disabling its own guard.
3. **Secret redaction** — API keys, tokens, and PEM blocks are masked before the payload
   reaches the classifier. Nothing sensitive is logged or sent to the LLM.
4. **LLM classification** — the redacted tool input is sent to a local Ollama model with an
   action-guard prompt. The model returns `BLOCK - <reason>` or `ALLOW`. Timeout fails open.
""")
    with col2:
        st.markdown("**PostToolUse (after execution)**")
        st.markdown("""
1. **IPI regex scan** — tool output is scanned against a blocklist of known prompt-injection
   phrases ("ignore previous instructions", "act as DAN", etc.). Match → instant `BLOCK_AUDITED`.
2. **LLM injection detection** — the output is sent to the local model with an injection-guard
   prompt that looks for instruction overrides, jailbreaks, and context manipulation.
3. PostToolUse verdicts are **always observation-only** (`BLOCK_AUDITED`) — the tool has already
   run, so the guard logs the threat and surfaces it in the dashboard rather than blocking.
""")

    st.markdown("---")

    # ── Verdict Types ──
    st.markdown("### Verdict Types")
    verdicts = [
        ("ALLOW", "#2ecc71", "LLM approved the action."),
        ("ALLOWLISTED", "#3b82f6", "Regex fast-path matched a known-safe command."),
        ("BLOCK", "#e74c3c", "Guard blocked the tool call (PreToolUse, enforcement mode)."),
        ("BLOCK_AUDITED", "#f59e0b", "Threat detected and logged; not enforced (PostToolUse or audit-only mode)."),
        ("ERROR", "#94a3b8", "LLM timed out or crashed — guard fails open and logs the error."),
    ]
    for verdict, colour, description in verdicts:
        badge = f'<span style="background:{colour};color:#1a1b26;padding:2px 10px;border-radius:4px;font-size:0.8rem;font-weight:700;">{verdict}</span>'
        st.markdown(f"{badge} &nbsp; {description}", unsafe_allow_html=True)

    st.markdown("---")

    # ── Inspection Methods ──
    st.markdown("### Inspection Methods")
    methods = [
        ("LLM", "#a855f7", "Local Ollama model classifies the full tool input or output."),
        ("REGEX", "#f97316", "Fast pattern match against IPI blocklist — no LLM call."),
        ("ALLOWLIST", "#3b82f6", "Regex allowlist matched a read-only command — no LLM call."),
        ("PATH", "#14b8a6", "Protected-path check blocked a write to a sensitive config file."),
    ]
    for method, colour, description in methods:
        badge = f'<span style="background:{colour};color:#1a1b26;padding:2px 10px;border-radius:4px;font-size:0.8rem;font-weight:700;">{method}</span>'
        st.markdown(f"{badge} &nbsp; {description}", unsafe_allow_html=True)

    st.markdown("---")

    # ── Shadow AI Discovery ──
    st.markdown("### Shadow AI Discovery")
    st.markdown("""
The **Shadow AI** scan audits your entire machine for AI agent installations and their security
posture, independent of any live hook traffic.

**Phase 1 — Inventory**
- **Agent detection** probes 10 installation surfaces: npm globals, PATH, pip packages, VS Code
  extensions, and agent-specific home-directory configs (Cursor, Windsurf, Claude Desktop, etc.).
- **Config crawler** walks the filesystem for `.claude/settings.json` and `.gemini/settings.json`,
  resolving the same parent-directory hook-inheritance chain the agents use at runtime.
- **MCP inventory** collects all registered MCP servers from five sources (Claude Desktop, global
  Claude/Gemini settings, extensions, and per-repo configs), classifying transport as `local` or
  `remote` and recording trust settings.

**Phase 2 — Analysis**
- **Gap analyzer** assigns each (repo × agent) pair a coverage status:
  - `COVERED` — at least one hook in the resolved chain is a known guard
  - `SHADOW_HOOK` — hooks exist but none are guard commands (unknown tool in the slot)
  - `UNGUARDED` — no hooks registered at all
- **Trust analyzer** generates findings (HIGH / MEDIUM / LOW) for: remote MCP servers with
  auto-trust, exposed API keys in env or `.env` files, overly broad folder-trust grants, orphaned
  hook binaries, and unguarded active agents.
""")

    st.markdown("---")

    # ── Enforcement Modes ──
    st.markdown("### Enforcement Modes")
    st.markdown("""
Controlled by `audit_only` in `coding_agent_guard/rules/config.yaml`:

| Mode | Behavior |
|---|---|
| `audit_only: true` *(default)* | BLOCK verdicts are logged but not enforced — the agent proceeds normally. Safe for initial rollout and evaluation. |
| `audit_only: false` | BLOCK verdicts terminate the tool call. Claude Code sees exit code `2`; Gemini CLI receives `{"decision": "deny"}`. |

The protected-path hard-block always enforces regardless of this setting — the guard's own
configuration files can never be modified by the agent it watches.
""")

    st.markdown("---")

    # ── Architecture ──
    st.markdown("### Component Map")
    st.code("""
coding_agent_guard/
├── core/
│   ├── guard.py          Main hook execution pipeline
│   ├── classifier.py     Ollama LLM integration (action & injection prompts)
│   ├── allowlist.py      Regex fast-path for read-only commands
│   ├── redactor.py       Secret masking (API keys, tokens, PEM blocks)
│   ├── telemetry.py      Append-only JSONL audit logging
│   └── config.py         YAML config loader
├── adapters/
│   ├── base.py           Agent detection, exit helpers
│   ├── claude.py         Claude Code adapter (exit 0 / exit 2)
│   └── gemini.py         Gemini CLI adapter (JSON decision object)
├── discovery/
│   ├── scanner.py        Orchestrates all Shadow AI probes
│   ├── agents.py         Detects installed AI agents
│   ├── config_crawler.py Parses agent configs & resolves hook inheritance
│   ├── gap_analyzer.py   Determines COVERED / SHADOW_HOOK / UNGUARDED status
│   ├── mcp_inventory.py  Enumerates MCP servers across all sources
│   ├── trust_analyzer.py Generates security findings
│   └── report.py         Text & JSON output formatters
├── rules/
│   ├── config.yaml       Guard model, timeouts, enforcement mode
│   └── patterns.yaml     IPI blocklist, protected paths, allowlist patterns
└── ui/
    └── dashboard.py      This Streamlit dashboard
""", language="text")

    st.markdown("""
Full architecture documentation is in the `docs/` directory:
- `docs/hooks_architecture.md` — Hook interception & inspection deep-dive
- `docs/shadow_ai_architecture.md` — Shadow AI discovery strategy & data models
""")


# ── Main Entry ────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="Coding Agent Guard Dashboard", layout="wide")

    cfg = Config()
    # Resolve audit_path relative to project cwd.
    audit_path = (Path.cwd() / cfg.audit_path).resolve()

    st.markdown("## 🛡️ Coding Agent Guard Dashboard")
    st.caption(f"Inspecting audit logs from: `{audit_path}`")

    tab_feed, tab_explorer, tab_dashboard, tab_shadow, tab_how = st.tabs([
        "Live Feed", "Audit Explorer", "Security Dashboard", "Shadow AI", "How it Works",
    ])

    with tab_feed:
        _render_live_feed(str(audit_path))

    with tab_explorer:
        _render_audit_explorer(str(audit_path))

    with tab_dashboard:
        _render_dashboard(str(audit_path))

    with tab_shadow:
        _render_shadow_ai(str(audit_path))

    with tab_how:
        _render_how_it_works()


if __name__ == "__main__":
    main()
