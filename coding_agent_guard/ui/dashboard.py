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
    "BLOCK_AUDITED": "#F59E0B", # mango yellow
    "ERROR":       "#E0AF68",   # amber
}

_VERDICT_ICON = {
    "ALLOW":       "ALLOW",
    "ALLOWLISTED": "SKIP",
    "BLOCK":       "BLOCK",
    "BLOCK_AUDITED": "AUDIT",
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


# ── Coverage matrix (static) ─────────────────────────────────────────────────

_COVERAGE_ROWS = [
    ("Bash",        "PreToolUse + PostToolUse", "Yes",     "Primary risk surface"),
    ("Edit",        "PreToolUse",               "Yes",     "File modification"),
    ("Write",       "PreToolUse",               "Yes",     "File creation / overwrite"),
    ("WebFetch",    "PreToolUse",               "Yes",     "Network egress, indirect injection"),
    ("Read",        "—",                        "No",      "Read-only, no state change"),
    ("Glob",        "—",                        "No",      "Read-only filesystem search"),
    ("Grep",        "—",                        "No",      "Read-only content search"),
    ("WebSearch",   "—",                        "No",      "No side effects"),
    ("Agent",       "—",                        "Partial", "Worktree isolation may break inheritance"),
    ("mcp__*",      "PreToolUse",               "Yes",     "Full tool_input JSON sent to guard model"),
    ("NotebookEdit","—",                        "No",      "Out of scope"),
]


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

def _generate_dashboard_markdown(df: pd.DataFrame, sessions: dict) -> str:
    """Generate a Markdown report summarizing the dashboard KPIs and analytics."""
    total       = len(df)
    blocks      = (df["verdict"] == "BLOCK").sum()
    errors      = (df["verdict"] == "ERROR").sum()
    block_rate  = blocks / total * 100 if total else 0
    session_cnt = df["session_id"].nunique()
    agent_cnt   = df["agent"].nunique() if "agent" in df.columns else 1
    avg_latency = df.loc[df["verdict"].isin(["ALLOW", "BLOCK"]), "latency_ms"].mean()

    lines = []
    lines.append("# Coding Agent Guard — Security Analytics Report")
    lines.append(f"**Report Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append("")
    
    lines.append("## Executive Summary (All-Time)")
    lines.append(f"- **Total Hook Events:** {total:,}")
    lines.append(f"- **Active Sessions:** {session_cnt:,}")
    lines.append(f"- **Agents Monitored:** {agent_cnt:,}")
    lines.append(f"- **Blocked Actions:** {blocks:,} ({block_rate:.1f}%)")
    lines.append(f"- **Avg Guard Latency:** {avg_latency:.0f} ms" if not pd.isna(avg_latency) else "- **Avg Guard Latency:** —")
    lines.append("")

    lines.append("## Events by Agent")
    agent_counts = df["agent"].fillna("Claude").value_counts()
    for agent, count in agent_counts.items():
        lines.append(f"- **{agent}:** {count:,}")
    lines.append("")

    lines.append("## Top 10 Blocked Inputs")
    blocked_df = df[df["verdict"] == "BLOCK"].copy()
    if blocked_df.empty:
        lines.append("No blocks recorded.")
    else:
        blocked_df["preview"] = blocked_df.apply(_tool_input_preview, axis=1)
        top_blocked = blocked_df["preview"].value_counts().head(10)
        lines.append("| Count | Input Preview |")
        lines.append("| :--- | :--- |")
        for preview, count in top_blocked.items():
            lines.append(f"| {count} | `{preview}` |")
    lines.append("")

    lines.append("## Session History")
    if sessions:
        lines.append("| Session | Branch | Commit | Events | Blocks | Started |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for sid, meta in sessions.items():
            sess_df = df[df["session_id"] == sid]
            short_sid = sid[:8]
            branch = meta.get("git_branch") or "—"
            commit = meta.get("git_commit") or "—"
            started = meta.get("timestamp", "—")
            lines.append(f"| {short_sid} | {branch} | {commit} | {len(sess_df)} | {int((sess_df['verdict'] == 'BLOCK').sum())} | {started} |")
    
    return "\n".join(lines)


def _render_dashboard(audit_path: str) -> None:
    df, sessions = _load_audit(audit_path)

    # ── Coverage indicator (always visible even when no data) ─────────────────
    with st.sidebar:
        with st.expander("Hook coverage", expanded=False):
            cov_df = pd.DataFrame(
                _COVERAGE_ROWS,
                columns=["Tool", "Hook type", "Covered", "Notes"],
            )
            st.dataframe(
                cov_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Covered": st.column_config.TextColumn(width="small"),
                },
            )
            st.caption("MCP tools and subagent worktrees are not covered in Phase 1.")

    if df.empty:
        st.info("No audit records yet. Start a session with hooks configured.")
        return

    # ── Export ────────────────────────────────────────────────────────────────
    col_t1, col_t2 = st.columns([10, 2])
    col_t1.markdown("### 📊 Security Analytics")
    report_md = _generate_dashboard_markdown(df, sessions)
    col_t2.download_button(
        label="📥 Export Report (MD)",
        data=report_md,
        file_name=f"coding_agent_guard_analytics_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        mime="text/markdown",
    )

    # ── Top-level KPIs ────────────────────────────────────────────────────────
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
    k6.metric("Avg guard latency", f"{avg_latency:.0f} ms" if not pd.isna(avg_latency) else "—")

    st.divider()

    col_left, col_mid, col_right = st.columns(3)

    # ── Events by Agent ───────────────────────────────────────────────────────
    with col_left:
        st.markdown("**Events by Agent**")
        agent_counts = df["agent"].fillna("Claude").value_counts().reset_index()
        agent_counts.columns = ["Agent", "Count"]
        st.bar_chart(agent_counts.set_index("Agent"), width="stretch")

    # ── Block rate over time (by day) ─────────────────────────────────────────
    with col_mid:
        st.markdown("**Block rate over time (daily)**")
        daily = df.copy()
        daily["date"] = daily["timestamp"].dt.date
        by_day = daily.groupby("date").agg(
            total=("verdict", "count"),
            blocks=("verdict", lambda x: (x == "BLOCK").sum()),
        ).reset_index()
        by_day["block_rate_%"] = (by_day["blocks"] / by_day["total"] * 100).round(1)
        st.line_chart(by_day.set_index("date")["block_rate_%"], width="stretch")

    # ── Verdict distribution (keeping Plotly pie as it adds interactive value) 
    with col_right:
        st.markdown("**Verdict distribution**")
        verdict_counts = df["verdict"].value_counts().reset_index()
        verdict_counts.columns = ["Verdict", "Count"]
        fig = px.pie(verdict_counts, values="Count", names="Verdict", 
                     color="Verdict", color_discrete_map=_VERDICT_COLOUR)
        fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=220)
        st.plotly_chart(fig, use_container_width=True)

    col_left2, col_mid2, col_right2 = st.columns(3)

    # ── Inspection Method distribution ───────────────────────────────────────
    with col_left2:
        st.markdown("**Inspection method distribution**")
        if "inspection_method" in df.columns:
            method_counts = df["inspection_method"].fillna("unknown").value_counts().reset_index()
            method_counts.columns = ["Method", "Count"]
            st.bar_chart(method_counts.set_index("Method"), width="stretch")
        else:
            st.caption("No inspection_method data yet.")

    # ── Tool type breakdown ───────────────────────────────────────────────────
    with col_mid2:
        st.markdown("**Events by tool type**")
        tool_counts = df["tool_name"].value_counts().reset_index()
        tool_counts.columns = ["Tool", "Count"]
        st.bar_chart(tool_counts.set_index("Tool"), width="stretch")

    # ── Top blocked inputs ────────────────────────────────────────────────────
    with col_right2:
        st.markdown("**Top 10 blocked inputs**")
        blocked_df = df[df["verdict"] == "BLOCK"].copy()
        if blocked_df.empty:
            st.success("No blocks recorded yet.")
        else:
            blocked_df["preview"] = blocked_df.apply(_tool_input_preview, axis=1)
            top_blocked = blocked_df["preview"].value_counts().head(10).reset_index()
            top_blocked.columns = ["Input preview", "Count"]
            st.dataframe(top_blocked, width="stretch", hide_index=True)

    # ── Hook latency histogram ────────────────────────────────────────────────
    st.markdown("**Guard model latency distribution (ALLOW + BLOCK calls only)**")
    latency_df = df[df["verdict"].isin(["ALLOW", "BLOCK"]) & df["latency_ms"].notna()]
    if latency_df.empty:
        st.caption("No latency data yet.")
    else:
        p50 = latency_df["latency_ms"].quantile(0.50)
        p95 = latency_df["latency_ms"].quantile(0.95)
        p99 = latency_df["latency_ms"].quantile(0.99)
        lc1, lc2, lc3 = st.columns(3)
        lc1.metric("P50 latency", f"{p50:.0f} ms")
        lc2.metric("P95 latency", f"{p95:.0f} ms")
        lc3.metric("P99 latency", f"{p99:.0f} ms")
        st.bar_chart(
            latency_df["latency_ms"].value_counts().sort_index(),
            width="stretch",
        )

    # ── Session summary ───────────────────────────────────────────────────────
    st.markdown("**Session summary**")
    if sessions:
        sess_rows = []
        for sid, meta in sessions.items():
            sess_df = df[df["session_id"] == sid]
            sess_rows.append({
                "Session":    _short_session(sid),
                "Branch":     meta.get("git_branch") or "—",
                "Commit":     meta.get("git_commit") or "—",
                "Events":     len(sess_df),
                "Blocks":     int((sess_df["verdict"] == "BLOCK").sum()),
                "Errors":     int((sess_df["verdict"] == "ERROR").sum()),
                "Started":    meta.get("timestamp", "—"),
                "Guard model": meta.get("hook_model") or "—",
            })
        st.dataframe(
            pd.DataFrame(sess_rows),
            width="stretch",
            hide_index=True,
        )


# ── Tab: Shadow AI ────────────────────────────────────────────────────────────

_SEV_COLOUR = {
    "HIGH":   "#F7768E",
    "MEDIUM": "#E0AF68",
    "LOW":    "#9ECE6A",
    "INFO":   "#7AA2F7",
}

_STATUS_COLOUR = {
    "COVERED":        "#9ECE6A",
    "BROKEN_HOOK":    "#FF6B6B",   # Bright red — looks covered but isn't
    "SHADOW_HOOK":    "#E0AF68",
    "ARTIFACT_ONLY":  "#7AA2F7",   # Blue for passive/artifacts
    "EXTERNAL_BRAIN": "#BB9AF7",   # Purple for external discovery
    "UNGUARDED":      "#F7768E",
}

_CAPABILITY_TIER_COLOUR = {
    "exec":        "#F7768E",   # red
    "network":     "#E0AF68",   # amber
    "write-local": "#FF9E64",   # orange
    "read-only":   "#9ECE6A",   # green
}

_STATUS_ORD = ["UNGUARDED", "BROKEN_HOOK", "EXTERNAL_BRAIN", "ARTIFACT_ONLY", "SHADOW_HOOK", "COVERED"]


def _sev_badge(severity: str) -> str:
    colour = _SEV_COLOUR.get(severity, "#888888")
    return f'<span style="background:{colour};color:#1a1b26;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700;">{severity}</span>'


def _status_badge(status: str) -> str:
    colour = _STATUS_COLOUR.get(status, "#888888")
    return f'<span style="background:{colour};color:#1a1b26;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700;">{status}</span>'


def _load_all_shadow_scans(audit_path: str) -> list[dict]:
    """Return all DISCOVERY_SCAN records from the audit file, oldest first."""
    scan_file = Path(audit_path) / "shadow_ai_scans.jsonl"
    scans: list[dict] = []
    if not scan_file.exists():
        return scans
    try:
        with open(scan_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("event_type") == "DISCOVERY_SCAN":
                        scans.append(rec)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return scans


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

    from coding_agent_guard.discovery.scanner import run_scan
    from coding_agent_guard.discovery.report import as_markdown
    # We need a ScanResult object to use as_markdown, but 'scan' is a dict from JSONL.
    # Re-parsing it fully is complex, so we'll just check if we can generate it from the dict.
    # Actually, as_markdown is simple enough that I should probably make it handle both or
    # just create a simple helper in dashboard.py if needed.
    # Let's see if I can re-run scan root if needed or just use a dict-based generator.
    
    summary = scan.get("summary", {})
    ts = _fmt_timestamp(scan.get("timestamp", "—"))

    # ── Export ────────────────────────────────────────────────────────────────
    col_t1, col_t2 = st.columns([10, 2])
    col_t1.caption(
        f"Last scan: **{ts}** \u2022 Root: `{scan.get('scan_root', '—')}` \u2022 "
        f"Scan ID: `{scan.get('scan_id', '—')}`"
    )
    
    # Full-page markdown export matching everything rendered on the tab
    def _scan_dict_to_markdown(s: dict) -> str:
        lines = []
        lines.append(f"# AI Posture & Discovery Report — {s.get('scan_id', '—')}")
        lines.append(f"**Scan Root:** `{s.get('scan_root', '—')}`  ")
        lines.append(f"**Timestamp:** {_fmt_timestamp(s.get('timestamp', '—'))}  ")
        lines.append(f"**Scan ID:** `{s.get('scan_id', '—')}`  ")
        lines.append(f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
        lines.append("")

        # ── Executive Summary ──────────────────────────────────────────────────
        summ = s.get("summary", {})
        score = summ.get("posture_maturity_score", 0)
        lines.append("## Executive Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("| :--- | :--- |")
        lines.append(f"| IDEs Detected | {summ.get('ides_found', 0)} |")
        lines.append(f"| CLI Agents Detected | {summ.get('agents_found', 0)} |")
        lines.append(f"| Repo / Agent Pairs | {summ.get('repo_agent_pairs', 0)} |")
        lines.append(f"| Covered | {summ.get('covered', 0)} |")
        lines.append(f"| Broken Hooks | {summ.get('broken_hooks', 0)} |")
        lines.append(f"| Shadow Hooks | {summ.get('shadow_hooks', 0)} |")
        lines.append(f"| Passive Monitoring (Artifacts) | {summ.get('artifact_only', 0)} |")
        lines.append(f"| Unguarded | {summ.get('unguarded', 0)} |")
        lines.append(f"| MCP Servers | {summ.get('mcp_servers', 0)} |")
        lines.append(f"| Remote MCPs (trust=true) | {summ.get('remote_mcps_trust_true', 0)} |")
        lines.append(f"| High Severity Findings | {summ.get('high_findings', 0)} |")
        lines.append(f"| Medium Severity Findings | {summ.get('medium_findings', 0)} |")
        lines.append(f"| Low Severity Findings | {summ.get('low_findings', 0)} |")
        lines.append(f"| **Posture Maturity Score** | **{score:.1f}%** |")
        lines.append("")

        # ── Posture Drift ──────────────────────────────────────────────────────
        all_scans_local = _load_all_shadow_scans(audit_path)
        if len(all_scans_local) >= 2:
            from coding_agent_guard.discovery.scanner import diff_scans as _diff_scans
            drift = _diff_scans(all_scans_local[-1], all_scans_local[-2])
            delta = drift["posture_score_delta"]
            sign = "+" if delta >= 0 else ""
            lines.append("## Posture Drift (vs Previous Scan)")
            lines.append("")
            lines.append(f"| Field | Value |")
            lines.append(f"| :--- | :--- |")
            lines.append(f"| Previous Scan ID | `{drift.get('from_scan_id', '—')}` |")
            lines.append(f"| Previous Timestamp | {_fmt_timestamp(drift.get('from_timestamp', '—'))} |")
            lines.append(f"| Score Delta | {sign}{delta:.1f}% |")
            if drift["new_agents"]:
                lines.append(f"| New Agents Detected | {', '.join(drift['new_agents'])} |")
            if drift["removed_agents"]:
                lines.append(f"| Agents No Longer Found | {', '.join(drift['removed_agents'])} |")
            if drift["new_mcp_servers"]:
                lines.append(f"| New MCP Servers | {', '.join(x['name'] for x in drift['new_mcp_servers'])} |")
            lines.append("")
            if drift["newly_unprotected"]:
                lines.append("### Repos That LOST Protection")
                lines.append("")
                lines.append("| Repo | Agent | Old Status | New Status |")
                lines.append("| :--- | :--- | :--- | :--- |")
                for r in drift["newly_unprotected"]:
                    lines.append(f"| `{r['repo_path']}` | {r['agent']} | {r['old_status']} | {r['new_status']} |")
                lines.append("")
            if drift["newly_protected"]:
                lines.append("### Repos That GAINED Protection")
                lines.append("")
                lines.append("| Repo | Agent | Old Status | New Status |")
                lines.append("| :--- | :--- | :--- | :--- |")
                for r in drift["newly_protected"]:
                    lines.append(f"| `{r['repo_path']}` | {r['agent']} | {r['old_status']} | {r['new_status']} |")
                lines.append("")

        # ── Findings ───────────────────────────────────────────────────────────
        findings = sorted(s.get("findings", []), key=lambda f: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(f.get("severity", ""), 9))
        lines.append(f"## Security Findings ({len(findings)})")
        lines.append("")
        if findings:
            for f in findings:
                sev = f.get("severity", "?")
                lines.append(f"### {sev}: {f.get('category', '')} ({f.get('id', '?')})")
                if f.get("agent"):
                    lines.append(f"- **Agent:** {f['agent']}")
                lines.append(f"- **Source:** `{f.get('source', '')}`")
                lines.append(f"- **Detail:** {f.get('detail', '')}")
                lines.append(f"- **Remediation:** {f.get('remediation', '')}")
                lines.append("")
        else:
            lines.append("No findings — posture looks clean.")
            lines.append("")

        # ── Coverage Map ───────────────────────────────────────────────────────
        coverage = s.get("coverage_map", [])
        _STATUS_ORD_EXP = {"UNGUARDED": 0, "BROKEN_HOOK": 1, "ARTIFACT_ONLY": 2, "SHADOW_HOOK": 3, "COVERED": 4}
        coverage_sorted = sorted(
            coverage,
            key=lambda g: (_STATUS_ORD_EXP.get(g.get("status", ""), 9), g.get("agent", ""), g.get("repo_path", "")),
        )
        lines.append(f"## Hook Coverage Map ({len(coverage)} repo/agent pairs)")
        lines.append("")
        if coverage_sorted:
            lines.append("| Status | Agent | Inherited | Hook Healthy | Hook | Repo |")
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for g in coverage_sorted:
                healthy = g.get("hook_healthy")
                healthy_str = "yes" if healthy is True else ("no" if healthy is False else "—")
                arts = f" *(Artifacts: {', '.join(g['artifact_files'])})*" if g.get("artifact_files") else ""
                lines.append(
                    f"| {g.get('status', '')} | {g.get('agent', '')} | "
                    f"{'yes' if g.get('inherited') else 'no'} | {healthy_str} | "
                    f"`{_hook_display_name(g.get('hook_command'))}` | "
                    f"`{g.get('repo_path', '')}`{arts} |"
                )
            lines.append("")
        else:
            lines.append("No coverage data.")
            lines.append("")

        # ── Agent Inventory ────────────────────────────────────────────────────
        agents = s.get("agents", [])
        lines.append(f"## Agent Inventory ({len(agents)})")
        lines.append("")
        if agents:
            lines.append("| Name | Version | Type | Method | Auth |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for a in agents:
                name = a.get("name", "")
                method = a.get("install_method", "")
                is_ide = any(x in name.lower() for x in ["vscode", "vs code", "zed", "antigravity", "cursor", "windsurf"])
                type_str = "IDE / Workspace" if is_ide else ("CI/CD Pipeline" if method == "ci_pipeline" else ("Extension" if method == "vscode_extension" else "CLI Agent"))
                lines.append(f"| {name} | {a.get('version') or '—'} | {type_str} | {method} | {a.get('auth_type') or '—'} |")
            lines.append("")
        else:
            lines.append("No agents detected.")
            lines.append("")

        # ── MCP Surface ────────────────────────────────────────────────────────
        mcps = s.get("mcp_servers", [])
        lines.append(f"## MCP Surface ({len(mcps)} server(s))")
        lines.append("")
        if mcps:
            lines.append("| Name | Agent | Transport | Capability Risk | Trust | Endpoint | Tools |")
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            for srv in mcps:
                tier = (srv.get("capability_tier") or "—").upper()
                trust = "YES ⚠" if srv.get("trust") else "no"
                endpoint = srv.get("url") or Path(srv.get("command", "").split()[0]).name if srv.get("command") else "—"
                tools = str(srv.get("tool_count")) if srv.get("tool_count") is not None else "—"
                lines.append(f"| {srv.get('name', '')} | {srv.get('agent', '')} | {srv.get('transport', '')} | {tier} | {trust} | `{endpoint}` | {tools} |")
            lines.append("")
        else:
            lines.append("No MCP servers configured.")
            lines.append("")

        return "\n".join(lines)

    shadow_report_md = _scan_dict_to_markdown(scan)
    col_t2.download_button(
        label="📥 Export Report (MD)",
        data=shadow_report_md,
        file_name=f"shadow_ai_report_{scan.get('scan_id', 'scan')}.md",
        mime="text/markdown",
    )

    # ── Metric row ────────────────────────────────────────────────────────────
    m0, m1, m2, m3, m3a, m4, m5, m6, m7, m8 = st.columns(10)
    m0.metric("IDEs",         summary.get("ides_found", 0))
    m1.metric("Agents",       summary.get("agents_found", 0))
    m2.metric("Pairs",        summary.get("repo_agent_pairs", 0))   # repo × agent
    m3.metric("Covered",      summary.get("covered", 0))
    m3a.metric("Artifacts",   summary.get("artifact_only", 0))
    m4.metric("Unguarded",    summary.get("unguarded", 0))
    m5.metric("MCP Servers",  summary.get("mcp_servers", 0))
    m6.metric("High",         summary.get("high_findings", 0))
    m7.metric("Medium",       summary.get("medium_findings", 0))
    
    score = summary.get("posture_maturity_score", 0)
    m8.metric("Maturity", f"{score:.0f}%")

    st.divider()

    # ── Posture Score Trend ───────────────────────────────────────────────────
    all_scans = _load_all_shadow_scans(audit_path)
    if len(all_scans) >= 2:
        trend_rows = []
        for s in all_scans:
            ts_raw = s.get("timestamp", "")
            try:
                ts = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except Exception:
                continue
            trend_rows.append({
                "Timestamp": ts,
                "Maturity Score (%)": round(s.get("summary", {}).get("posture_maturity_score", 0), 1),
            })
        if trend_rows:
            trend_df = pd.DataFrame(trend_rows).set_index("Timestamp")
            col_trend, col_diff = st.columns([2, 1])
            with col_trend:
                st.markdown("**Posture Maturity Score — Trend**")
                fig_trend = px.line(
                    trend_df.reset_index(),
                    x="Timestamp",
                    y="Maturity Score (%)",
                    markers=True,
                )
                fig_trend.update_layout(
                    margin=dict(t=10, b=10, l=0, r=0),
                    height=220,
                    yaxis=dict(range=[0, 105]),
                )
                st.plotly_chart(fig_trend, use_container_width=True)

            # ── Scan Diff ─────────────────────────────────────────────────────
            with col_diff:
                st.markdown("**Drift vs Previous Scan**")
                from coding_agent_guard.discovery.scanner import diff_scans as _diff_scans
                drift = _diff_scans(all_scans[-1], all_scans[-2])
                delta = drift["posture_score_delta"]
                sign = "+" if delta >= 0 else ""
                color = "#9ECE6A" if delta >= 0 else "#F7768E"
                st.markdown(
                    f'<div style="font-size:2rem;font-weight:700;color:{color};">{sign}{delta:.1f}%</div>',
                    unsafe_allow_html=True,
                )
                if drift["new_agents"]:
                    st.warning(f"New agents: {', '.join(drift['new_agents'])}")
                if drift["newly_unprotected"]:
                    for r in drift["newly_unprotected"]:
                        st.error(f"Lost protection: {r['agent']} @ {Path(r['repo_path']).name}")
                if drift["newly_protected"]:
                    for r in drift["newly_protected"]:
                        st.success(f"Gained protection: {r['agent']} @ {Path(r['repo_path']).name}")
                if drift["new_mcp_servers"]:
                    st.warning(f"New MCPs: {[s['name'] for s in drift['new_mcp_servers']]}")
                if not any([drift["new_agents"], drift["removed_agents"], drift["newly_unprotected"],
                            drift["newly_protected"], drift["new_mcp_servers"], drift["removed_mcp_servers"]]):
                    st.success("No changes since last scan.")
        st.divider()

    # ── Education Section ─────────────────────────────────────────────────────
    with st.expander("🎓 **Research Brief: Understanding Passive Monitoring & Posture Maturity**", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Defense Layers")
            st.markdown("""
- **Layer 1: Active Enforcement (Hooks)**  
  Interceptor scripts are registered in agent settings. Every tool call is halted until the Guard model returns `ALLOW`.  
  *Agents: Claude Code, Gemini CLI.*

- **Layer 2: Passive Monitoring (Digital Exhaust Audit)**  
  The agent is detected via version-controlled artifacts (`task.md`) or active "Brain Sessions" in your home directory (`~/.gemini/antigravity/brain/`). The Guard audits this "Digital Exhaust" to map agent intent to project workspaces.  
  *Agents: Antigravity, VS Code AI.*
""")
        with c2:
            st.markdown("##### Posture Maturity Score")
            st.markdown("""
The **Maturity Score** is a security research heuristic used to grade AI adoption safety:
- **100%**: Full hook interception across all agents.
- **50%**: Passive observation (Artifacts) only — risk of "Shadow Actions".
- **0%**: No guard presence; unmonitored tool surface.

**The "Missing Link":** To move IDE agents from Layer 2 to Layer 1, use the `shell_guard` wrapper or MCP shim.
""")
    
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
        _STATUS_ORD = {"UNGUARDED": 0, "BROKEN_HOOK": 1, "ARTIFACT_ONLY": 2, "SHADOW_HOOK": 3, "COVERED": 4}
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
            agent = row.get("agent", "")
            
            # Emojis for consistency
            is_ide_agent = any(x in agent.lower() for x in ["zed", "antigravity", "cursor", "windsurf"])
            agent_display = f"🖥️ {agent}" if is_ide_agent else f"🤖 {agent}"

            rows.append({
                "Status":    row.get("status", ""),
                "Agent":     agent_display,
                "Repo":      repo_name,
                "Artifacts": ", ".join(row.get("artifact_files", [])) or "—",
                "Hook":      _hook_display_name(row.get("hook_command")),
                "Inherited": "yes" if row.get("inherited") else "no",
            })

        df_cov = pd.DataFrame(rows)

        broken_count = sum(1 for r in coverage if r.get("status") == "BROKEN_HOOK")
        if broken_count:
            st.error(
                f"{broken_count} repo(s) have a BROKEN_HOOK — guard is registered but the binary is missing. "
                "These appear covered but tool calls pass through uninspected."
            )

        if unguarded_count == 0 and broken_count == 0:
            # Happy path: collapse the big table, surface a clear pass message
            st.success(
                f"All {len(sorted_cov)} repo/agent pairs are protected by Coding Agent Guard."
            )
            with st.expander("Show coverage details", expanded=False):
                st.dataframe(df_cov, width='stretch', hide_index=True)
        else:
            # Something is unguarded or broken — show the full table so problems are visible
            st.dataframe(df_cov, width='stretch', hide_index=True)
    else:
        st.info("No coverage data.")

    st.divider()

    # ── Agent Inventory ───────────────────────────────────────────────────────
    agents = scan.get("agents", [])
    st.markdown(f"#### Agent Inventory ({len(agents)})")
    if agents:
        ide_rows = []
        agent_rows = []

        for a in agents:
            name = a.get("name", "")
            method = a.get("install_method", "")
            
            # Categorization logic
            is_ide = any(x in name.lower() for x in ["vscode", "vs code", "zed", "antigravity", "cursor", "windsurf"])
            
            row = {
                "Name":    f"🖥️ {name}" if is_ide else f"🤖 {name}",
                "Version": a.get("version") or "—",
                "Type":    "IDE / Workspace" if is_ide else ("Extension" if method == "vscode_extension" else "CLI Agent"),
                "Method":  method,
                "Auth":    a.get("auth_type") or "—",
            }

            if is_ide:
                ide_rows.append(row)
            else:
                agent_rows.append(row)

        if ide_rows:
            st.markdown("**AI-Powered IDEs & Workspaces**")
            st.dataframe(pd.DataFrame(ide_rows), width='stretch', hide_index=True)
        
        if agent_rows:
            st.markdown("**Autonomous Agents & Extensions**")
            st.dataframe(pd.DataFrame(agent_rows), width='stretch', hide_index=True)
    else:
        st.info("No agents detected.")

    # ── MCP Surface ───────────────────────────────────────────────────────────
    mcps = scan.get("mcp_servers", [])
    st.markdown(f"#### MCP Surface ({len(mcps)} server(s))")
    if mcps:
        rows = []
        for s in mcps:
            trust = s.get("trust", False)
            tier = s.get("capability_tier") or "—"
            rows.append({
                "Name":             s.get("name", ""),
                "Agent":            s.get("agent", ""),
                "Transport":        s.get("transport", ""),
                "Capability Risk":  tier.upper() if tier != "—" else "—",
                "Trust":            "⚠ YES" if trust else "no",
                "Endpoint":         _mcp_endpoint_display(s),
                "Tools":            s.get("tool_count") if s.get("tool_count") is not None else "—",
            })
        st.dataframe(rows, width='stretch', hide_index=True)

        # Warn about high-risk tiers
        exec_servers = [s["name"] for s in mcps if s.get("capability_tier") == "exec"]
        net_servers = [s["name"] for s in mcps if s.get("capability_tier") == "network"]
        if exec_servers:
            st.error(f"EXEC-tier MCP servers detected (can run code/shell): {', '.join(exec_servers)}")
        if net_servers:
            st.warning(f"NETWORK-tier MCP servers detected (can make outbound requests): {', '.join(net_servers)}")
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
  - `ARTIFACT_ONLY` — agent detected via artifacts; passive monitoring active (IDE agents)
  - `SHADOW_HOOK` — hooks exist but none are guard commands (unknown tool in the slot)
  - `UNGUARDED` — no hooks registered at all

**Phase 3 — Advanced Research**
- **Posture Maturity Score** calculates a heuristic safety grade (0–100%) by weighting Active Enforcement vs. Passive Observation.
- **External Brain Discovery** probes the machine's local agent memory (`~/.gemini/antigravity/brain/`) to identify agents that have been "cleaned" from the repository.
- **Intent Drift Analysis** flags discrepancies between an agent's stated plan in its brain session and its actual actions on disk.
- **Artifact Proliferation** maps the physical footprint of AI agents across the filesystem.
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

    tab_how, tab_feed, tab_explorer, tab_dashboard, tab_shadow = st.tabs([
        "📘 System Blueprint", "📡 Live Feed", "🔍 Forensics & Logs", "📊 Dashboard", "🛡️ AI Posture & Discovery",
    ])

    with tab_how:
        _render_how_it_works()

    with tab_feed:
        _render_live_feed(str(audit_path))

    with tab_explorer:
        _render_audit_explorer(str(audit_path))

    with tab_dashboard:
        _render_dashboard(str(audit_path))

    with tab_shadow:
        _render_shadow_ai(str(audit_path))


if __name__ == "__main__":
    main()
