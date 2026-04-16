import glob
import json
import datetime
from pathlib import Path

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
        keyword = st.text_input("Search tool input", key="ae_keyword", placeholder="e.g. rm -rf, curl, .env")
        st.divider()

    # Apply filters
    filtered = df.copy()
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
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.markdown("**Events by tool type**")
        tool_counts = df["tool_name"].value_counts().head(10).reset_index()
        tool_counts.columns = ["Tool", "Count"]
        st.bar_chart(tool_counts.set_index("Tool"), width="stretch")


# ── Main Entry ────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="Coding Agent Guard Dashboard", layout="wide")
    
    cfg = Config()
    # Resolve audit_path relative to project cwd.
    audit_path = (Path.cwd() / cfg.audit_path).resolve()

    st.markdown("## 🛡️ Coding Agent Guard Dashboard")
    st.caption(f"Inspecting audit logs from: `{audit_path}`")

    tab_feed, tab_explorer, tab_dashboard = st.tabs([
        "Live Feed", "Audit Explorer", "Security Dashboard",
    ])

    with tab_feed:
        _render_live_feed(str(audit_path))

    with tab_explorer:
        _render_audit_explorer(str(audit_path))

    with tab_dashboard:
        _render_dashboard(str(audit_path))


if __name__ == "__main__":
    main()
