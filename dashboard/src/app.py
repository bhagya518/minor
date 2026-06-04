import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime
import concurrent.futures

# Dynamic node discovery
SEED_NODE = "http://127.0.0.1:8000"

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

@st.cache_data(ttl=60)
def discover_nodes(seed_node=SEED_NODE):
    discovered_nodes = set()
    nodes_to_check = [seed_node]
    while nodes_to_check:
        node_url = nodes_to_check.pop()
        if node_url in discovered_nodes: continue
        peers_data = _get(f"{node_url}/peers", timeout=1)
        if peers_data:
            peers = peers_data.get("peers") or peers_data.get("peer_list")
            if isinstance(peers, dict):
                for peer_id, peer_info in peers.items():
                    addr = peer_info.get("node_address") or f"{peer_info.get('host')}:{peer_info.get('port')}"
                    peer_url = f"http://{addr}"
                    if peer_url not in discovered_nodes: nodes_to_check.append(peer_url)
            elif isinstance(peers, list):
                for peer_info in peers:
                    addr = f"{peer_info.get('host')}:{peer_info.get('port')}"
                    peer_url = f"http://{addr}"
                    if peer_url not in discovered_nodes: nodes_to_check.append(peer_url)
        discovered_nodes.add(node_url)
    return list(discovered_nodes)

def fmt_ts(ts):
    if not ts: return "—"
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        if isinstance(ts, str):
            try:
                return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
            except ValueError:
                return datetime.fromisoformat(ts.replace('Z', '+00:00')).strftime("%H:%M:%S")
        return str(ts)
    except Exception:
        return str(ts)[:10] if ts else "—"

def tier_style(action):
    tiers = {
        "ALLOW": "🟢 ALLOW",
        "WARN": "🟡 WARN",
        "QUARANTINE": "🟠 QUARANTINE",
        "SLASHED": "🔴 SLASH"
    }
    return tiers.get(action, "⚪ SYNC")

def fetch_node_snapshot(base_url):
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        fh  = ex.submit(_get, f"{base_url}/health")
        ft  = ex.submit(_get, f"{base_url}/trust")
        fc  = ex.submit(_get, f"{base_url}/consensus/reputations")
        fmr = ex.submit(_get, f"{base_url}/monitoring/results")
        fr  = ex.submit(_get, f"{base_url}/reports/latest?limit=20")
    return {
        "health": fh.result(), "trust": ft.result(),
        "consensus": fc.result(), "mon_results": fmr.result(),
        "reports": fr.result(), "base_url": base_url
    }

def mon_results_to_rows(mon_data):
    if not mon_data: return []
    results = mon_data.get("results", mon_data)
    if isinstance(results, dict): results = list(results.values())
    if not isinstance(results, list): return []
    return [{
        "URL": r.get("url", "—"),
        "Status": "🟢 UP" if (r.get("status") == "success" or r.get("is_reachable")) else "🔴 DOWN",
        "HTTP": r.get("status_code") or r.get("http_status") or "—",
        "Response ms": round(r.get("response_ms") or r.get("response_time_ms") or 0, 1),
        "SSL": "✅" if r.get("ssl_valid") else "❌",
        "Timestamp": fmt_ts(r.get("timestamp", ""))
    } for r in results if isinstance(r, dict)]

@st.fragment(run_every=5)
def live_dashboard(ALL_NODES):
    with st.spinner(f"Synchronizing with {len(ALL_NODES)} nodes..."):
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(ALL_NODES))) as ex:
            all_snaps = list(ex.map(fetch_node_snapshot, ALL_NODES))

    all_health = [s["health"] for s in all_snaps if s["health"] and "error" not in s["health"]]
    all_trust = [s["trust"] for s in all_snaps if s["trust"] and "error" not in s["trust"]]
    all_cons = [s["consensus"] for s in all_snaps if s["consensus"] and "error" not in s["consensus"]]
    all_mon_res = [s["mon_results"] for s in all_snaps if s["mon_results"] and "error" not in s["mon_results"]]
    all_reports = [s["reports"] for s in all_snaps if s["reports"] and "error" not in s["reports"]]

    if not all_health:
        st.error("❌ No nodes responding. Ensure your node cluster is running.")
        return

    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Nodes Online", f"🟢 {len(all_health)}")
    avg_rep = np.mean([t.get('trust_score', 0) for t in all_trust]) if all_trust else 0.9
    m2.metric("Network Health", f"{avg_rep*100:.1f}% Trust")
    m3.metric("Epoch Cycle", "5 Seconds")
    st.divider()

    tabs = st.tabs(["🌍 Global Website Status", "🛡️ Node Reputation Leaderboard"])

    with tabs[0]:
        st.subheader("Live Uptime Monitoring")
        all_rows = []
        for mon_res, reports in zip(all_mon_res, all_reports):
            rows = mon_results_to_rows(mon_res)
            if not rows and reports:
                reps = reports.get("reports", [])
                rows = [{
                    "URL": r.get("url"), "Status": "🟢 UP" if r.get("is_reachable") else "🔴 DOWN",
                    "HTTP": r.get("status_code", "—"), "Response ms": round(r.get("response_ms", 0), 1),
                    "SSL": "✅" if r.get("ssl_valid") else "❌", "Timestamp": fmt_ts(r.get("timestamp", ""))
                } for r in reps]
            all_rows.extend(rows)

        if all_rows:
            df = pd.DataFrame(all_rows)
            df_grouped = df.groupby('URL').agg({
                'Status': 'first', 'HTTP': 'first', 'Response ms': 'mean',
                'SSL': 'first', 'Timestamp': 'max'
            }).reset_index()
            
            for _, row in df_grouped.iterrows():
                cols = st.columns([3, 1, 1, 1, 1, 2])
                cols[0].markdown(f"**{row['URL']}**")
                cols[1].markdown(row["Status"])
                cols[2].markdown(f"`{row['HTTP']}`")
                cols[3].markdown(f"⏱ {row['Response ms']:.0f} ms")
                cols[4].markdown(f"SSL {row['SSL']}")
                cols[5].caption(f"Checked: {row['Timestamp']}")
                st.divider()
            
            fig_rt = px.bar(df_grouped, x="URL", y="Response ms", 
                           title="Avg Latency (ms) Across All Nodes", 
                           color_discrete_sequence=['#3498db'])
            st.plotly_chart(fig_rt, use_container_width=True)
        else:
            st.info("No monitoring data. Initializing first epoch...")

    with tabs[1]:
        st.subheader("Global Node Leaderboard")
        all_reps = {}
        all_shards = {}
        for cons in all_cons:
            reps = cons.get("reputations", {})
            actions = cons.get("mitigation_actions", {})
            for nid, val in reps.items():
                all_reps[nid] = val
                shard_info = actions.get(nid, {})
                all_shards[nid] = shard_info
        
        if all_reps:
            rep_rows = []
            for nid, val in sorted(all_reps.items(), key=lambda x: x[1], reverse=True):
                action_data = all_shards.get(nid, {})
                action = action_data.get("action", "ALLOW") if isinstance(action_data, dict) else "ALLOW"
                
                rep_rows.append({
                    "Node Identifier": nid, 
                    "Reputation Score": round(val, 4),
                    "System Tier": tier_style(action),
                    "Current Shard": action_data.get("shard", "PRIMARY") if isinstance(action_data, dict) else "PRIMARY"
                })
            
            st.table(pd.DataFrame(rep_rows))
            
            df_rep = pd.DataFrame(rep_rows)
            fig_rep = px.bar(df_rep, x="Node Identifier", y="Reputation Score",
                            color="Reputation Score", 
                            color_continuous_scale="RdYlGn", 
                            range_y=[0, 1],
                            title="Network Reputation Distribution")
            st.plotly_chart(fig_rep, use_container_width=True)
        else:
            st.info("Nodes are syncing reputation state...")

def main():
    st.set_page_config(page_title="🔍 Web Monitor Dashboard", layout="wide")
    st.title("🔍 Decentralized Website Monitoring")
    st.caption("Clean Performance View: Uptime & Node Reputation")
    
    ALL_NODES = discover_nodes()
    
    with st.sidebar:
        st.header("⚙️ Controls")
        if st.button("▶ Trigger Fresh Scan", use_container_width=True):
            for node_url in ALL_NODES:
                _post(f"{node_url}/monitor", {"urls": ["https://google.com", "https://github.com", "https://httpbin.org"]})
            st.success("Monitoring triggered!")
        
        st.divider()
        st.caption(f"Network: {len(ALL_NODES)} Active Nodes")
        st.caption("Live-sync enabled via @st.fragment")

    # The fragment will auto-rerun without blocking the sidebar
    live_dashboard(ALL_NODES)

if __name__ == "__main__":
    main()
