import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import polars as pl
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="BTC Quant Intelligence", layout="wide", page_icon=":chart_with_upwards_trend:")

ROOT = os.path.dirname(os.path.dirname(__file__))

# ── CSS tweaks ──
st.markdown("""
<style>
    .decision-buy { color: #3fb950; font-size: 28px; font-weight: bold; }
    .decision-watch { color: #4ecdc4; font-size: 28px; font-weight: bold; }
    .decision-wait { color: #8b949e; font-size: 28px; font-weight: bold; }
    .decision-caution { color: #ff6b6b; font-size: 28px; font-weight: bold; }
    .decision-sell { color: #f85149; font-size: 28px; font-weight: bold; }
    .metric-bullish { color: #3fb950; font-weight: bold; }
    .metric-bearish { color: #f85149; font-weight: bold; }
    .metric-neutral { color: #8b949e; }
    .stMetric { background-color: #161b22; border-radius: 8px; padding: 8px; }
    section[data-testid="stSidebar"] { background-color: #0d1117; }
    .stApp { background-color: #0e1117; }
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] { background-color: #161b22; border-radius: 4px 4px 0 0; padding: 8px 16px; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_data():
    dfs = {}
    for mod, path in [
        ("whale", f"{ROOT}/whale/whale_signals.csv"),
        ("vp", f"{ROOT}/volume_price/vp_signals.csv"),
        ("sm", f"{ROOT}/smart_money/smart_money_signals.csv"),
    ]:
        df = pl.read_csv(path, try_parse_dates=True).sort("start_time")
        dfs[mod] = df
    return dfs


def align(dfs):
    w = dfs["whale"].select(["start_time", "composite_whale_score", "whale_momentum",
        "reserve_zscore", "sig_reserve", "sig_netflow", "exchange_whale_ratio",
        "netflow_7d_sum", "stable_zscore", "fund_flow_ratio", "mpi"
    ]).rename({"composite_whale_score": "w_score", "whale_momentum": "w_mom",
               "reserve_zscore": "w_reserve_z", "exchange_whale_ratio": "w_ratio",
               "netflow_7d_sum": "w_netflow", "stable_zscore": "w_stable_z"})

    v = dfs["vp"].select(["start_time", "vp_signal", "vp_momentum",
        "close", "volume", "vol_zscore_90d", "obv_price_corr_30d",
        "vol_5d_ma", "vol_20d_ma",
    ]).rename({"vp_signal": "v_score", "vp_momentum": "v_mom",
               "vol_zscore_90d": "v_vol_z", "obv_price_corr_30d": "v_obv_corr",
               "vol_5d_ma": "v_vol_5d", "vol_20d_ma": "v_vol_20d"})

    s = dfs["sm"].select(["start_time", "composite_sm_score", "sm_momentum",
        "cpi_zscore", "tbsr_zscore", "funding_zscore", "oi",
        "sig_cpi_taker_div", "oi_7d_chg", "px_7d_chg",
    ]).rename({"composite_sm_score": "s_score", "sm_momentum": "s_mom",
               "cpi_zscore": "s_cpi_z", "tbsr_zscore": "s_taker_z",
               "funding_zscore": "s_funding_z", "sig_cpi_taker_div": "s_cpi_div"})

    all_t = pl.concat([w.select("start_time"), v.select("start_time"), s.select("start_time")]).unique().sort("start_time")
    j = all_t.join(w, on="start_time", how="left").join(v, on="start_time", how="left").join(s, on="start_time", how="left")
    j = j.with_columns([
        (pl.col("w_score") / 2.0).clip(-2, 2).alias("w_norm"),
        pl.col("v_score").clip(-2, 2).alias("v_norm"),
        (pl.col("s_score") / 1.5).clip(-2, 2).alias("s_norm"),
    ])
    j = j.with_columns([
        (pl.col("w_norm").fill_null(0) + pl.col("v_norm").fill_null(0) + pl.col("s_norm").fill_null(0)).alias("overall"),
    ])
    return j


def get_decision(overall, w, v, s):
    if overall >= 3:    return "BUY", "3fb950", "Strong buy — follow the trend", "ADD (DCA more)"
    elif overall >= 1:  return "WATCH", "4ecdc4", "Buy bias — consider entry", "DCA (keep normal)"
    elif overall >= -1: return "WAIT", "8b949e", "No direction — stay out", "HODL (do nothing)"
    elif overall >= -3: return "CAUTION", "ff6b6b", "Sell pressure — reduce risk", "PAUSE DCA (watch)"
    else:               return "SELL", "f85149", "Strong sell — hedge or exit", "REDUCE 30-50%"


def gauge_chart(val, title, key):
    val = max(-3, min(3, float(val) if val is not None else 0))
    color = "#3fb950" if val > 0 else ("#f85149" if val < 0 else "#8b949e")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val,
        number={"font": {"size": 36, "color": color}, "suffix": ""},
        gauge={
            "axis": {"range": [-3, 3], "tickwidth": 0},
            "bar": {"color": color, "thickness": 0.2},
            "steps": [
                {"range": [-3, -1], "color": "rgba(248,81,73,0.3)"},
                {"range": [-1, 1], "color": "rgba(139,148,158,0.15)"},
                {"range": [1, 3], "color": "rgba(63,185,80,0.3)"},
            ],
            "threshold": {"line": {"color": "white", "width": 2}, "value": val},
        },
        title={"text": title, "font": {"size": 12, "color": "#c9d1d9"}},
    ))
    fig.update_layout(height=160, margin=dict(t=30, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#c9d1d9"))
    st.plotly_chart(fig, use_container_width=True, key=key)


def plot_overall_history(d):
    fig = go.Figure()
    colors = ["#3fb950" if v > 0 else ("#f85149" if v < 0 else "#484f58") for v in d["overall"]]
    fig.add_trace(go.Bar(x=d["start_time"], y=d["overall"], marker_color=colors,
                         name="Overall", hovertemplate="%{x|%Y-%m-%d}<br>Score: %{y:+.1f}<extra></extra>"))
    fig.add_hline(y=3, line_dash="dot", line_color="#3fb950", opacity=0.3, annotation_text="BUY zone")
    fig.add_hline(y=-3, line_dash="dot", line_color="#f85149", opacity=0.3, annotation_text="SELL zone")
    fig.add_hline(y=0, line_color="#484f58", line_width=1)
    fig.update_layout(height=350, margin=dict(t=10, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#c9d1d9"), xaxis_title=None, yaxis_title="Score",
                      hovermode="x unified", bargap=0.1,
                      xaxis=dict(gridcolor="#21262d"), yaxis=dict(gridcolor="#21262d"))
    st.plotly_chart(fig, use_container_width=True, key="overall_history")


def plot_module_scores(d):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, subplot_titles=("Whale", "Volume-Price", "Smart Money"),
                        vertical_spacing=0.08)
    for i, (col, title) in enumerate([("w_norm", "Whale"), ("v_norm", "VP"), ("s_norm", "SM")]):
        vals = d[col].fill_null(0)
        colors = ["#3fb950" if v > 0 else ("#f85149" if v < 0 else "#484f58") for v in vals]
        fig.add_trace(go.Bar(x=d["start_time"], y=vals, marker_color=colors, name=title,
                             hovertemplate="%{x|%Y-%m-%d}<br>%{y:+.1f}<extra></extra>"), row=i+1, col=1)
        fig.add_hline(y=0, line_color="#484f58", line_width=1, row=i+1, col=1)
    fig.update_layout(height=450, margin=dict(t=30, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#c9d1d9"), showlegend=False, hovermode="x unified",
                      xaxis=dict(gridcolor="#21262d"), yaxis=dict(gridcolor="#21262d", range=[-3.5, 3.5]),
                      xaxis2=dict(gridcolor="#21262d"), yaxis2=dict(gridcolor="#21262d", range=[-3.5, 3.5]),
                      xaxis3=dict(gridcolor="#21262d"), yaxis3=dict(gridcolor="#21262d", range=[-3.5, 3.5]))
    st.plotly_chart(fig, use_container_width=True, key="module_scores")


def plot_whale_detail(d):
    fig = make_subplots(rows=2, cols=2, subplot_titles=(
        "Exchange Reserve Z-Score", "7-Day Netflow (BTC)",
        "Whale Ratio %", "Stablecoin Reserve Z-Score"
    ), vertical_spacing=0.15, horizontal_spacing=0.1)

    fig.add_trace(go.Scatter(x=d["start_time"], y=d["w_reserve_z"], line=dict(color="#58a6ff"),
                             name="Reserve Z", hovertemplate="%{y:+.2f}<extra></extra>"), row=1, col=1)

    nf = d["w_netflow"].fill_null(0)
    colors_nf = ["#3fb950" if v < 0 else "#f85149" for v in nf]
    fig.add_trace(go.Bar(x=d["start_time"], y=nf, marker_color=colors_nf,
                         name="Netflow", hovertemplate="%{y:+,.0f} BTC<extra></extra>"), row=1, col=2)

    fig.add_trace(go.Scatter(x=d["start_time"], y=d["w_ratio"] * 100, line=dict(color="#d2991d"),
                             name="Whale Ratio %", hovertemplate="%{y:.1f}%<extra></extra>"), row=2, col=1)

    fig.add_trace(go.Scatter(x=d["start_time"], y=d["w_stable_z"], line=dict(color="#39d353"),
                             name="Stablecoin Z", hovertemplate="%{y:+.2f}<extra></extra>"), row=2, col=2)

    fig.update_layout(height=400, margin=dict(t=30, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#c9d1d9"), showlegend=False, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, key="whale_detail")


def plot_vp_detail(d):
    fig = make_subplots(rows=2, cols=2, subplot_titles=(
        "Price & Volume", "OBV-Price Correlation (30d)",
        "Volume MAs (5d/20d/50d)", "Volume Z-Score"
    ), vertical_spacing=0.15, horizontal_spacing=0.1)

    fig.add_trace(go.Scatter(x=d["start_time"], y=d["close"], line=dict(color="#1f6feb", width=1.5),
                             name="Close", yaxis="y"), row=1, col=1)
    fig.add_trace(go.Bar(x=d["start_time"], y=d["volume"], marker_color="rgba(88,166,255,0.3)",
                         name="Volume", yaxis="y2"), row=1, col=1)

    fig.add_trace(go.Scatter(x=d["start_time"], y=d["v_obv_corr"], line=dict(color="#a371f7"),
                             name="OBV Corr", hovertemplate="%{y:.2f}<extra></extra>"), row=1, col=2)

    fig.add_trace(go.Scatter(x=d["start_time"], y=d["v_vol_5d"], line=dict(color="#58a6ff"),
                             name="5d MA"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d["start_time"], y=d["v_vol_20d"], line=dict(color="#1f6feb"),
                             name="20d MA"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d["start_time"], y=d["v_vol_20d"].fill_null(0), line=dict(color="#484f58", dash="dot"),
                             name="50d MA"), row=2, col=1)  # approximate

    fig.add_trace(go.Bar(x=d["start_time"], y=d["v_vol_z"],
                         marker_color=["#f85149" if z > 0 else "#3fb950" for z in d["v_vol_z"].fill_null(0)],
                         name="Vol Z"), row=2, col=2)

    fig.update_layout(height=400, margin=dict(t=30, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#c9d1d9"), showlegend=False, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, key="vp_detail")


def plot_sm_detail(d):
    fig = make_subplots(rows=2, cols=2, subplot_titles=(
        "Coinbase Premium Z vs Taker Z", "Funding Rate Z-Score",
        "Open Interest vs Price", "CPI-Taker Divergence"
    ), vertical_spacing=0.15, horizontal_spacing=0.1)

    fig.add_trace(go.Scatter(x=d["start_time"], y=d["s_cpi_z"], line=dict(color="#3fb950"),
                             name="CPI Z"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d["start_time"], y=d["s_taker_z"], line=dict(color="#d2991d"),
                             name="Taker Z"), row=1, col=1)

    fig.add_trace(go.Scatter(x=d["start_time"], y=d["s_funding_z"], line=dict(color="#a371f7"),
                             name="Funding Z"), row=1, col=2)

    fig.add_trace(go.Scatter(x=d["start_time"], y=d["close"], line=dict(color="#1f6feb", width=1.5),
                             name="Price", yaxis="y"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d["start_time"], y=d["oi"].fill_null(0) / 1e9, line=dict(color="#a371f7"),
                             name="OI ($B)", yaxis="y2"), row=2, col=1)

    cpi_div = d["s_cpi_div"].fill_null(0)
    colors_cd = ["#f85149" if v < 0 else ("#3fb950" if v > 0 else "#484f58") for v in cpi_div]
    fig.add_trace(go.Bar(x=d["start_time"], y=cpi_div, marker_color=colors_cd,
                         name="CPI-Taker Div"), row=2, col=2)

    fig.update_layout(height=400, margin=dict(t=30, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#c9d1d9"), showlegend=False, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, key="sm_detail")


# ══════════════════ MAIN APP ══════════════════

st.title(":chart_with_upwards_trend: BTC Quantitative Intelligence Dashboard")

# Load data
dfs = load_data()
df = align(dfs)
latest = df.tail(1).to_dicts()[0]
overall = latest.get("overall", 0) or 0
w, v, s = latest.get("w_norm", 0) or 0, latest.get("v_norm", 0) or 0, latest.get("s_norm", 0) or 0
btc_price = latest.get("close")
decision, decolor, dec_detail, hodl = get_decision(overall, w, v, s)

# Sidebar: date range selector
st.sidebar.header(":calendar: Time Range")
days = st.sidebar.slider("Days of history", 30, 365, 180, step=30)
last_date = df["start_time"].tail(1).to_list()[0]
cutoff = last_date - pl.duration(days=days)
d = df.filter(df["start_time"] >= cutoff).to_pandas()

# Sidebar: Info
st.sidebar.markdown("---")
st.sidebar.markdown("### How to read")
st.sidebar.markdown("""
| Score | Trade | HODL |
|-------|-------|------|
| +3~+6 | BUY | ADD |
| +1~+3 | WATCH | DCA |
| -1~+1 | WAIT | HODL |
| -3~-1 | CAUTION | PAUSE |
| -6~-3 | SELL | REDUCE |
""")

# ═══ HEADER ROW ═══
col1, col2, col3, col4, col5, col6 = st.columns([1.2, 1, 1, 0.8, 1.2, 1])
with col1:
    st.metric("BTC Price", f"${btc_price:,.0f}" if btc_price else "N/A")
with col2:
    st.metric("Overall", f"{overall:+.1f}")
with col3:
    st.metric("Trade", decision, delta_color="off")
with col4:
    st.metric("HODL", hodl)
with col5:
    st.metric("Whale", f"{w:+.1f}")
with col6:
    st.metric("Smart $", f"{s:+.1f}")

# Decision banner
st.markdown(f"""
<div style="background-color:#161b22; border-radius:8px; padding:12px 20px; margin:8px 0;
            border-left:4px solid #{decolor};">
    <span style="font-size:22px;font-weight:bold;color:#{decolor};">{decision}</span>
    <span style="color:#8b949e; margin-left:16px; font-size:14px;">{dec_detail}</span>
    <span style="color:#8b949e; margin-left:8px; font-size:13px;"> | HODL: {hodl}</span>
</div>
""", unsafe_allow_html=True)

# ═══ GAUGES ═══
g1, g2, g3 = st.columns(3)
with g1:
    gauge_chart(w, "Whale Accumulation", "g_w")
with g2:
    gauge_chart(v, "Volume-Price Divergence", "g_v")
with g3:
    gauge_chart(s, "Smart Money", "g_s")

# ═══ OVERALL HISTORY ═══
st.subheader("Overall Score History")
plot_overall_history(d)

# ═══ TABS: Module Details ═══
st.subheader("Module Details")
tab1, tab2, tab3 = st.tabs([":whale: Whale Flow", ":bar_chart: Volume-Price", ":bank: Smart Money"])

with tab1:
    plot_module_scores(d)
    st.markdown("---")
    st.subheader("Whale Indicators")
    plot_whale_detail(d)

with tab2:
    st.subheader("Volume-Price Indicators")
    plot_vp_detail(d)

with tab3:
    st.subheader("Smart Money Indicators")
    plot_sm_detail(d)

# ═══ FOOTER ═══
st.markdown("---")
st.caption(f"Last updated: {last_date} | Data sources: CryptoQuant, Glassnode | Modules refresh: run whale/vp/sm modules")
