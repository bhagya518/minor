import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime
import concurrent.futures

# ─── Config ───────────────────────────────────────────────────────────────────
SEED_NODE = "http://127.0.0.1:8000"

ACTION_STYLE = {
    "ALLOW":      {"icon": "🟢", "color": "#22c55e", "bg": "#052e16"},
    "WARN":       {"icon": "🟡", "color": "#f59e0b", "bg": "#1c1004"},
    "QUARANTINE": {"icon": "🟠", "color": "#f97316", "bg": "#1a0700"},
    "SLASHED":    {"icon": "🔴", "color": "#ef4444", "bg": "#200a0a"},
}
SHARD_PALETTE = [
    "#6366f1", "#06b6d4", "#8b5cf6", "#10b981",
    "#f59e0b", "#ec4899", "#14b8a6", "#f97316",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _get(url, timeout=5):
    try:
        r = requests.get(url, timeout=timeout)
        return r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def _post(url, payload, timeout=30):
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

@st.cache_data(ttl=10)
def discover_nodes(seed_node=SEED_NODE):
    discovered = set()
    queue = [seed_node]
    while queue:
        url = queue.pop().replace("localhost", "127.0.0.1")
        if url in discovered:
            continue
        peers_data = _get(f"{url}/peers", timeout=5)
        if peers_data and "error" not in peers_data:
            peers = peers_data.get("peers") or peers_data.get("peer_list")
            if isinstance(peers, dict):
                for _, info in peers.items():
                    addr = info.get("node_address") or f"{info.get('host')}:{info.get('port')}"
                    peer_url = f"http://{addr}".replace("localhost", "127.0.0.1")
                    if peer_url not in discovered:
                        queue.append(peer_url)
            elif isinstance(peers, list):
                for info in peers:
                    addr = f"{info.get('host')}:{info.get('port')}"
                    peer_url = f"http://{addr}".replace("localhost", "127.0.0.1")
                    if peer_url not in discovered:
                        queue.append(peer_url)
        discovered.add(url)
    return list(discovered)

def fmt_ts(ts):
    if not ts:
        return "—"
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        if isinstance(ts, str):
            try:
                return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
            except ValueError:
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
        return str(ts)
    except Exception:
        return str(ts)[:10] if ts else "—"

def tier_badge(action: str) -> str:
    st_info = ACTION_STYLE.get(action, {"icon": "⚪", "color": "#888"})
    return f'{st_info["icon"]} {action}'

def fetch_node_snapshot(base_url):
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
        fh     = ex.submit(_get, f"{base_url}/health")
        ft     = ex.submit(_get, f"{base_url}/trust")
        fc     = ex.submit(_get, f"{base_url}/consensus/reputations")
        fmr    = ex.submit(_get, f"{base_url}/monitoring/results")
        fr     = ex.submit(_get, f"{base_url}/reports/latest?limit=20")
        fsh    = ex.submit(_get, f"{base_url}/sharding/status")
        fhist  = ex.submit(_get, f"{base_url}/sharding/history?limit=20")
        fstats = ex.submit(_get, f"{base_url}/sharding/stats")
    return {
        "health":       fh.result(),
        "trust":        ft.result(),
        "consensus":    fc.result(),
        "mon_results":  fmr.result(),
        "reports":      fr.result(),
        "base_url":     base_url,
        "shard_status": fsh.result(),
        "shard_history":fhist.result(),
        "shard_stats":  fstats.result(),
    }

def mon_results_to_rows(mon_data):
    if not mon_data:
        return []
    results = mon_data.get("results", mon_data)
    if isinstance(results, dict):
        results = list(results.values())
    if not isinstance(results, list):
        return []
    return [{
        "URL":         r.get("url", "—"),
        "Status":      "🟢 UP" if (r.get("status") == "success" or r.get("is_reachable")) else "🔴 DOWN",
        "HTTP":        r.get("status_code") or r.get("http_status") or "—",
        "Response ms": round(r.get("response_ms") or r.get("response_time_ms") or 0, 1),
        "SSL":         "✅" if r.get("ssl_valid") else "❌",
        "Timestamp":   fmt_ts(r.get("timestamp", "")),
    } for r in results if isinstance(r, dict)]


# ─── Shard helpers ────────────────────────────────────────────────────────────
def _best_shard_status(all_snaps):
    """Pick the freshest /sharding/status that has real numbered shards."""
    for snap in all_snaps:
        ss = snap.get("shard_status", {})
        if isinstance(ss, dict) and "shards" in ss and ss.get("n_shards", 0) > 0:
            return ss
    # fallback: first non-error
    for snap in all_snaps:
        ss = snap.get("shard_status", {})
        if isinstance(ss, dict) and "shards" in ss:
            return ss
    return None

def _merge_shard_history(all_snaps):
    seen = set()
    combined = []
    for snap in all_snaps:
        hist = snap.get("shard_history", {})
        if isinstance(hist, dict):
            for entry in hist.get("history", []):
                eid = entry.get("epoch_id")
                if eid not in seen:
                    seen.add(eid)
                    combined.append(entry)
    return sorted(combined, key=lambda x: x.get("epoch_id", 0), reverse=True)

def _best_shard_stats(all_snaps):
    for snap in all_snaps:
        s = snap.get("shard_stats", {})
        if isinstance(s, dict) and s.get("total_reshuffles", 0) > 0:
            return s
    return {}


# ─── Shard card renderer (pure Streamlit – no HTML) ──────────────────────────
def render_shard_card(shard_id: int, shard_data: dict, color: str):
    """
    Renders a shard card using only native Streamlit widgets.

    ┌──────────────────────┐
    │ ⬡ SHARD 1            │
    │ Leader: node_X       │
    ├──────────────────────┤
    │ node_a  🟢 ALLOW     │
    │ node_b  🟡 WARN      │
    │ node_c  🟠 QUARANTINE│
    │ node_d  🔴 SLASHED   │
    └──────────────────────┘
    """
    leader  = shard_data.get("leader", "—")
    members = shard_data.get("members", [])
    count   = shard_data.get("count", len(members))

    with st.container(border=True):
        st.markdown(f"**⬡ SHARD {shard_id + 1}**")
        st.caption(f"Leader: `{leader or '—'}` · {count} nodes")

        if members:
            rows = []
            for m in members:
                if not isinstance(m, dict):
                    continue
                nid    = m.get("node_id", "—")
                rep    = m.get("reputation", 0.0)
                action = m.get("action", m.get("tier", "ALLOW"))
                ast    = ACTION_STYLE.get(action, {"icon": "⚪"})
                is_leader = (nid == leader)
                rows.append({
                    "Node":       f"👑 {nid}" if is_leader else nid,
                    "Status":     f"{ast['icon']} {action}",
                    "Reputation": round(rep, 4),
                })
            if rows:
                st.dataframe(
                    pd.DataFrame(rows),
                    width='stretch',
                    hide_index=True,
                )
        else:
            st.caption("No nodes assigned")


# ─── Main live fragment ────────────────────────────────────────────────────────
@st.fragment(run_every=5)
def live_dashboard(ALL_NODES):
    with st.spinner(f"Synchronizing with {len(ALL_NODES)} nodes..."):
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(ALL_NODES))) as ex:
            all_snaps = list(ex.map(fetch_node_snapshot, ALL_NODES))

    all_health   = [s["health"]     for s in all_snaps if s["health"]     and "error" not in s["health"]]
    all_trust    = [s["trust"]      for s in all_snaps if s["trust"]      and "error" not in s["trust"]]
    all_cons     = [s["consensus"]  for s in all_snaps if s["consensus"]  and "error" not in s["consensus"]]
    all_mon_res  = [s["mon_results"]for s in all_snaps if s["mon_results"]and "error" not in s["mon_results"]]
    all_reports  = [s["reports"]    for s in all_snaps if s["reports"]    and "error" not in s["reports"]]

    if not all_health:
        st.error("❌ No nodes responding. Ensure your node cluster is running.")
        return

    shard_status = _best_shard_status(all_snaps)

    # ── Top metrics ───────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🟢 Nodes Online",       len(all_health))
    avg_rep = np.mean([t.get("trust_score", 0) for t in all_trust]) if all_trust else 0.9
    c2.metric("🛡️ Network Health",     f"{avg_rep*100:.1f}%")
    c3.metric("⏱ Epoch Cycle",         "60 s")
    n_shards = shard_status.get("n_shards", 0) if shard_status else 0
    c4.metric("🔷 Active Shards",       n_shards if n_shards else "—")
    last_res = shard_status.get("last_reshuffle") if shard_status else None
    c5.metric("🔄 Last Reshuffle",      f"Epoch {last_res}" if last_res is not None else "Pending…")
    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tabs = st.tabs([
        "🌍 Website Uptime",
        "🛡️ Node Reputation",
        "🔷 Dynamic Sharding",
    ])

    # ── Tab 0: Uptime ─────────────────────────────────────────────────────────
    with tabs[0]:
        st.subheader("Live Uptime Monitoring")
        all_rows = []
        for mon_res, reports in zip(all_mon_res, all_reports):
            rows = mon_results_to_rows(mon_res)
            if not rows and reports:
                reps = reports.get("reports", [])
                rows = [{
                    "URL": r.get("url"),
                    "Status": "🟢 UP" if r.get("is_reachable") else "🔴 DOWN",
                    "HTTP": r.get("status_code", "—"),
                    "Response ms": round(r.get("response_ms", 0), 1),
                    "SSL": "✅" if r.get("ssl_valid") else "❌",
                    "Timestamp": fmt_ts(r.get("timestamp", "")),
                } for r in reps]
            all_rows.extend(rows)

        if all_rows:
            df = pd.DataFrame(all_rows)
            df_g = df.groupby("URL").agg({
                "Status": "first", "HTTP": "first",
                "Response ms": "mean", "SSL": "first", "Timestamp": "max",
            }).reset_index()
            for _, row in df_g.iterrows():
                cols = st.columns([3, 1, 1, 1, 1, 2])
                cols[0].markdown(f"**{row['URL']}**")
                cols[1].markdown(row["Status"])
                cols[2].markdown(f"`{row['HTTP']}`")
                cols[3].markdown(f"⏱ {row['Response ms']:.0f} ms")
                cols[4].markdown(f"SSL {row['SSL']}")
                cols[5].caption(f"Checked: {row['Timestamp']}")
                st.divider()
            fig_rt = px.bar(df_g, x="URL", y="Response ms",
                            title="Avg Latency (ms)",
                            color_discrete_sequence=["#6366f1"])
            st.plotly_chart(fig_rt, width='stretch')
        else:
            st.info("No monitoring data. Initializing first epoch…")

    # ── Tab 1: Reputation ─────────────────────────────────────────────────────
    with tabs[1]:
        st.subheader("Global Node Reputation Leaderboard")
        all_reps_map = {}
        all_shards_map = {}
        for cons in all_cons:
            for nid, val in cons.get("reputations", {}).items():
                all_reps_map[nid] = val
            for nid, act in cons.get("mitigation_actions", {}).items():
                all_shards_map[nid] = act

        if all_reps_map:
            rep_rows = []
            for nid, val in sorted(all_reps_map.items(), key=lambda x: x[1], reverse=True):
                action_data = all_shards_map.get(nid, {})
                action = action_data.get("action", "ALLOW") if isinstance(action_data, dict) else "ALLOW"
                shard_idx = None
                if shard_status and "assignment" in shard_status:
                    shard_idx = shard_status["assignment"].get(nid)
                rep_rows.append({
                    "Node":       nid,
                    "Reputation": round(val, 4),
                    "Status":     tier_badge(action),
                    "Shard":      f"SHARD {shard_idx+1}" if shard_idx is not None else "—",
                })
            st.table(pd.DataFrame(rep_rows))
            df_rep = pd.DataFrame(rep_rows)
            fig_rep = px.bar(df_rep, x="Node", y="Reputation",
                             color="Reputation", color_continuous_scale="RdYlGn",
                             range_y=[0, 1], title="Reputation Distribution")
            st.plotly_chart(fig_rep, width='stretch')
        else:
            st.info("Nodes are syncing reputation state…")

    # ── Tab 2: Dynamic Sharding ───────────────────────────────────────────────
    with tabs[2]:
        st.subheader("🔷 Dynamic Trust-Aware Sharding")
        st.caption(
            "Every **3 epochs**, nodes are reshuffled across numbered shards. "
            "Each shard receives a mix of ALLOW · WARN · QUARANTINE · SLASHED nodes "
            "to prevent malicious node concentration and validator collusion."
        )

        if not shard_status or "shards" not in shard_status:
            st.info(
                "⏳ Sharding data will appear after the first epoch consensus "
                "(≈60 s after cluster start). "
                "If the cluster just restarted, wait for epoch 3 for the first reshuffle."
            )
            st.stop()

        shards      = shard_status.get("shards", {})
        cur_epoch   = shard_status.get("current_epoch", "—")
        last_res    = shard_status.get("last_reshuffle", "—")
        interval    = shard_status.get("reshuffle_interval", 3)
        n_shards    = shard_status.get("n_shards", len(shards))

        # ── Summary strip ────────────────────────────────────────────────────
        sm1, sm2, sm3, sm4, sm5 = st.columns(5)
        sm1.metric("Current Epoch",        cur_epoch)
        sm2.metric("Last Reshuffle",        f"Epoch {last_res}")
        sm3.metric("Reshuffle Interval",    f"Every {interval} epochs")
        sm4.metric("Active Shards",         n_shards)
        total_nodes = sum(s.get("count", 0) for s in shards.values())
        sm5.metric("Total Tracked Nodes",   total_nodes)
        st.divider()

        # ── Shard cards ───────────────────────────────────────────────────────
        st.markdown("### 🗂 Current Shard Assignments")
        st.markdown(
            "_Each shard is intentionally **mixed**: every shard contains nodes from "
            "multiple trust tiers to ensure Byzantine fault tolerance._"
        )

        # Sort shards by numeric shard_id
        sorted_shards = sorted(
            shards.items(),
            key=lambda kv: int(kv[1].get("shard_id", kv[0]))
        )

        # Layout: 2 cards per row
        for i in range(0, len(sorted_shards), 2):
            row_shards = sorted_shards[i:i+2]
            cols = st.columns(len(row_shards))
            for col, (sid_str, shard_data) in zip(cols, row_shards):
                sid_int = shard_data.get("shard_id", 0)
                color = SHARD_PALETTE[sid_int % len(SHARD_PALETTE)]
                with col:
                    render_shard_card(sid_int, shard_data, color)

        st.divider()

        # ── Tier action distribution donut ────────────────────────────────────
        st.markdown("### 📊 Network-Wide Trust Tier Distribution")
        action_counts = {"ALLOW": 0, "WARN": 0, "QUARANTINE": 0, "SLASHED": 0}
        for sid_str, shard_data in shards.items():
            for m in shard_data.get("members", []):
                if isinstance(m, dict):
                    action = m.get("action", m.get("tier", "ALLOW"))
                    if action in action_counts:
                        action_counts[action] += 1

        donut_col, bar_col = st.columns([1, 1])
        with donut_col:
            if sum(action_counts.values()) > 0:
                fig_donut = go.Figure(go.Pie(
                    labels=list(action_counts.keys()),
                    values=list(action_counts.values()),
                    hole=0.6,
                    marker=dict(colors=[ACTION_STYLE[a]["color"] for a in action_counts]),
                    textinfo="label+value",
                    hovertemplate="%{label}: %{value} nodes (%{percent})<extra></extra>",
                ))
                fig_donut.update_layout(
                    showlegend=False,
                    height=320,
                    margin=dict(t=30, b=10, l=10, r=10),
                    title="Trust Tier Breakdown",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#e2e8f0",
                )
                st.plotly_chart(fig_donut, width='stretch')

        with bar_col:
            # Per-shard composition stacked bar
            shard_rows = []
            for sid_str, shard_data in sorted_shards:
                sid_int = shard_data.get("shard_id", 0)
                shard_action_counts = {"ALLOW": 0, "WARN": 0, "QUARANTINE": 0, "SLASHED": 0}
                for m in shard_data.get("members", []):
                    if isinstance(m, dict):
                        action = m.get("action", "ALLOW")
                        if action in shard_action_counts:
                            shard_action_counts[action] += 1
                for action, cnt in shard_action_counts.items():
                    shard_rows.append({
                        "Shard": f"SHARD {sid_int+1}",
                        "Action": action,
                        "Count": cnt,
                    })
            if shard_rows:
                df_comp = pd.DataFrame(shard_rows)
                fig_comp = px.bar(
                    df_comp, x="Shard", y="Count", color="Action",
                    color_discrete_map={a: ACTION_STYLE[a]["color"] for a in ACTION_STYLE},
                    barmode="stack",
                    title="Per-Shard Composition",
                    height=320,
                )
                fig_comp.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#e2e8f0",
                    legend_title="Trust Tier",
                )
                st.plotly_chart(fig_comp, width='stretch')

        st.divider()

        # ── Reshuffle history ─────────────────────────────────────────────────
        st.markdown("### 🕒 Reshuffle Audit Trail")
        history = _merge_shard_history(all_snaps)
        shard_stats = _best_shard_stats(all_snaps)

        if shard_stats:
            h1, h2, h3 = st.columns(3)
            h1.metric("Total Reshuffles",      shard_stats.get("total_reshuffles", 0))
            h2.metric("Total Node Moves",       shard_stats.get("total_node_moves", 0))
            h3.metric("Avg Moves/Reshuffle",    shard_stats.get("avg_moves_per_reshuffle", "—"))

        if history:
            hist_rows = []
            for entry in history:
                td   = entry.get("tier_dist", {})
                ldr  = entry.get("leaders", {})
                moves= entry.get("moved_nodes", [])
                hist_rows.append({
                    "Epoch":      entry.get("epoch_id", "—"),
                    "Time":       fmt_ts(entry.get("timestamp")),
                    "Shards":     entry.get("n_shards", "—"),
                    "Nodes":      entry.get("total_nodes", "—"),
                    "ALLOW":      td.get("PRIMARY", 0),
                    "WARN":       td.get("MONITORING", 0),
                    "QUARANTINE": td.get("QUARANTINE", 0),
                    "SLASHED":    td.get("SLASHED", 0),
                    "Moves":      len(moves),
                })
            df_hist = pd.DataFrame(hist_rows)
            st.dataframe(df_hist, width='stretch', hide_index=True)

            # History tier bar chart
            if len(hist_rows) >= 2:
                df_tier_hist = pd.melt(
                    df_hist,
                    id_vars=["Epoch"],
                    value_vars=["ALLOW", "WARN", "QUARANTINE", "SLASHED"],
                    var_name="Tier", value_name="Count",
                )
                fig_hist = px.bar(
                    df_tier_hist, x="Epoch", y="Count", color="Tier",
                    color_discrete_map={
                        "ALLOW":      ACTION_STYLE["ALLOW"]["color"],
                        "WARN":       ACTION_STYLE["WARN"]["color"],
                        "QUARANTINE": ACTION_STYLE["QUARANTINE"]["color"],
                        "SLASHED":    ACTION_STYLE["SLASHED"]["color"],
                    },
                    barmode="stack",
                    title="Trust Tier Distribution per Reshuffle Epoch",
                )
                fig_hist.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#e2e8f0",
                )
                st.plotly_chart(fig_hist, width='stretch')

            # Latest moves detail
            latest_moves = history[0].get("moved_nodes", []) if history else []
            if latest_moves:
                st.markdown("#### 🔀 Node Moves in Latest Reshuffle")
                move_rows = []
                for mv in latest_moves:
                    frm = mv.get("from_shard", "—")
                    to  = mv.get("to_shard", "—")
                    frm_label = f"SHARD {frm+1}" if isinstance(frm, int) else str(frm)
                    to_label  = f"SHARD {to+1}"  if isinstance(to,  int) else str(to)
                    action = mv.get("action", "ALLOW")
                    ast = ACTION_STYLE.get(action, {"icon": "⚪"})
                    move_rows.append({
                        "Node":       mv.get("node_id", "—"),
                        "Status":     f"{ast['icon']} {action}",
                        "From":       frm_label,
                        "To":         to_label,
                        "Reputation": mv.get("reputation", 0.0),
                    })
                st.dataframe(
                    pd.DataFrame(move_rows).style.format({"Reputation": "{:.4f}"}),
                    width='stretch',
                    hide_index=True,
                )
        else:
            st.info(
                "📋 Reshuffle history will appear here after the 3rd epoch cycle. "
                "The first reshuffle fires at epoch 3."
            )


# ─── App entry point ──────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="🔍 PoR Network Monitor",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Theme is controlled by Streamlit's built-in theming, no custom CSS needed

    st.title("🔍 Decentralized Website Monitoring")
    st.caption("Live · Node Reputation · Dynamic Trust-Aware Sharding")

    ALL_NODES = discover_nodes()

    with st.sidebar:
        st.header("⚙️ Controls")
        if st.button("▶ Trigger Fresh Scan", width='stretch'):
            for node_url in ALL_NODES:
                _post(f"{node_url}/monitor", {
                    "urls": ["https://google.com", "https://github.com", "https://httpbin.org"]
                })
            st.success("Monitoring triggered on all nodes!")
        st.divider()
        st.caption(f"🌐 Network: **{len(ALL_NODES)}** active nodes")
        st.caption("🔄 Auto-refresh every 5 s")

    live_dashboard(ALL_NODES)


if __name__ == "__main__":
    main()
