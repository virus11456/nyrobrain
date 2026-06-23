import os, sys
import numpy as np
import polars as pl

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from chart_style import apply_style, fmt_date_axis, get_colors
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

ROOT = os.path.dirname(os.path.dirname(__file__))
OUT_DIR = os.path.join(os.path.dirname(__file__), "assets")
C = get_colors()


def score_to_action(overall: float, w: float, v: float, s: float) -> dict:
    if overall >= 3:
        light, action, detail = "BUY", "Strong buy signal, follow the trend", "All modules aligned bullish"
        lth = "ADD (DCA more)"  # long-term holder
    elif overall >= 1:
        light, action, detail = "WATCH", "Moderate buy bias, consider entry", "Bullish tilt but not full conviction"
        lth = "DCA (keep normal)"
    elif overall >= -1:
        light, action, detail = "WAIT", "No clear direction, stay out", "Mixed signals, wait for clarity"
        lth = "HODL (do nothing)"
    elif overall >= -3:
        light, action, detail = "CAUTION", "Selling pressure building, reduce risk", "Bearish signals accumulating"
        lth = "PAUSE DCA (watch)"
    else:
        light, action, detail = "SELL", "Strong sell signal, hedge or exit", "All modules aligned bearish"
        lth = "REDUCE 30-50%"

    parts = []
    if w > 1:      parts.append("Whales accumulating")
    elif w < -1:   parts.append("Whales distributing")
    else:          parts.append("Whales neutral")
    if v > 0.5:    parts.append("Volume bullish")
    elif v < -0.5: parts.append("Volume bearish")
    else:          parts.append("Volume neutral")
    if s > 0.5:    parts.append("Institutions buying")
    elif s < -0.5: parts.append("Institutions selling")
    else:          parts.append("Institutions neutral")
    return {"light": light, "action": action, "detail": detail, "lth": lth, "summary": " | ".join(parts)}


def load_module_signals() -> dict[str, pl.DataFrame]:
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
    w = dfs["whale"].select([
        "start_time", "composite_whale_score", "whale_momentum",
        "reserve_zscore", "sig_reserve", "sig_netflow",
    ]).rename({"composite_whale_score": "w_score", "whale_momentum": "w_mom",
               "reserve_zscore": "w_reserve_z"})

    v = dfs["vp"].select([
        "start_time", "vp_signal", "vp_momentum",
        "close", "vol_zscore_90d", "obv_price_corr_30d",
    ]).rename({"vp_signal": "v_score", "vp_momentum": "v_mom",
               "vol_zscore_90d": "v_vol_z", "obv_price_corr_30d": "v_obv_corr"})

    s = dfs["sm"].select([
        "start_time", "composite_sm_score", "sm_momentum",
        "cpi_zscore", "tbsr_zscore", "sig_cpi_taker_div",
    ]).rename({"composite_sm_score": "s_score", "sm_momentum": "s_mom",
               "cpi_zscore": "s_cpi_z", "tbsr_zscore": "s_taker_z",
               "sig_cpi_taker_div": "s_cpi_taker_div"})

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


def summary(df):
    r = df.tail(1).to_dicts()[0]
    ov = r.get("overall", 0) or 0
    if ov >= 3:     st = "STRONG BULLISH"
    elif ov >= 1:   st = "MODERATE BULLISH"
    elif ov >= -1:  st = "NEUTRAL"
    elif ov >= -3:  st = "MODERATE BEARISH"
    else:           st = "STRONG BEARISH"
    return {
        "date": str(r["start_time"]),
        "status": st, "overall": round(ov, 2),
        "w_norm": round(r.get("w_norm", 0) or 0, 2),
        "v_norm": round(r.get("v_norm", 0) or 0, 2),
        "s_norm": round(r.get("s_norm", 0) or 0, 2),
        "close": r.get("close"),
    }


def plot_dashboard(df, s):
    os.makedirs(OUT_DIR, exist_ok=True)
    act = score_to_action(s["overall"], s["w_norm"], s["v_norm"], s["s_norm"])
    lt = df["start_time"].tail(1).to_list()[0]
    d = df.filter(df["start_time"] >= lt - np.timedelta64(270, "D")).sort("start_time")

    fig = plt.figure(figsize=(20, 17))
    gs = fig.add_gridspec(5, 5, height_ratios=[0.15, 1.2, 0.6, 2.0, 2.0],
                          hspace=0.45, wspace=0.4,
                          left=0.04, right=0.98, top=0.96, bottom=0.04)

    ov_color = C["green"] if s["overall"] > 0 else (C["red"] if s["overall"] < 0 else C["subtext"])

    # ═══ ROW 1: DECISION BAR ═══
    dbar = fig.add_subplot(gs[0, :])
    dbar.text(0.02, 0.5, f"TRADE: {act['light']}", fontsize=13, fontweight="bold",
              ha="left", va="center", color=ov_color)
    dbar.text(0.24, 0.5, f"| HODL: {act['lth']}", fontsize=11,
              ha="left", va="center", color=C["teal"])
    dbar.text(0.42, 0.5, f"{s['w_norm']:+.1f}|{s['v_norm']:+.1f}|{s['s_norm']:+.1f}",
    # score bar inline
              fontsize=11, ha="center", va="center", color=C["subtext"])
    dbar.text(0.62, 0.5, f"BTC ${s['close']:,.0f}" if s['close'] else "",
              fontsize=13, fontweight="bold", ha="center", va="center", color=C["text"])
    dbar.text(0.82, 0.5, act["summary"], fontsize=11, ha="right", va="center", color=C["subtext"])
    dbar.text(0.98, 0.5, s["date"][:10], fontsize=9, ha="right", va="center", color=C["gray"])
    dbar.axis("off")

    # ═══ ROW 2: THREE GAUGES ═══
    for col, (label, val) in enumerate([
        ("Whale\nAccumulation", s["w_norm"]),
        ("Volume-Price\nDivergence", s["v_norm"]),
        ("Smart\nMoney", s["s_norm"]),
    ]):
        ax = fig.add_subplot(gs[1, col + 1])
        _gauge(ax, val, label)

    # ═══ ROW 3: SCORE → ACTION LEGEND ═══
    legend_ax = fig.add_subplot(gs[2, :])
    _draw_legend_bar(legend_ax, s["overall"])

    # ═══ ROW 4: OVERALL SCORE HISTORY ═══
    ax_os = fig.add_subplot(gs[3, :2])
    ov = d["overall"].fill_null(0)
    c_ov = [C["green"] if v > 0 else (C["red"] if v < 0 else C["gray"]) for v in ov]
    ax_os.bar(d["start_time"], ov, color=c_ov, alpha=0.75, width=1.2)
    ax_os.axhline(0, color=C["gray"], linewidth=0.5)
    # Zone annotations
    for y, label, lc in [(3, "BUY zone", C["green"]), (-3, "SELL zone", C["red"])]:
        ax_os.axhline(y, color=lc, linestyle=":", linewidth=0.5, alpha=0.4)
        ax_os.text(d["start_time"][len(d)//2], y + 0.3, label, fontsize=7,
                   color=lc, ha="center", va="bottom", alpha=0.6)
    ax_os.set_ylim(-7, 7)
    ax_os.set_ylabel("Bearish  <-->  Bullish")
    ax_os.set_title("Overall Composite Score", fontweight="bold")
    fmt_date_axis(ax_os)

    # ═══ ROW 4: SCORE BREAKDOWN TABLE ═══
    ax_tb = fig.add_subplot(gs[3, 2:])
    _draw_score_table(ax_tb, s, act)

    # ═══ ROW 5: DETAIL SUB-PLOTS ═══
    # Whale: Reserve Z + Signal
    ax_w = fig.add_subplot(gs[4, 0])
    ax_w.plot(d["start_time"], d["w_reserve_z"].fill_null(0), color=C["blue"], linewidth=1.2)
    ax_w.axhline(0, color=C["gray"], linewidth=0.5)
    ax_w.set_title("Reserve Z-Score")
    fmt_date_axis(ax_w)

    ax_w2 = fig.add_subplot(gs[4, 1])
    ws = d["sig_reserve"].fill_null(0)
    c_ws = [C["green"] if v > 0.3 else (C["red"] if v < -0.3 else C["gray"]) for v in ws]
    ax_w2.bar(d["start_time"], ws, color=c_ws, alpha=0.6, width=1.2)
    ax_w2.axhline(0, color=C["gray"], linewidth=0.5)
    ax_w2.set_title("Whale Reserve Signal")
    fmt_date_axis(ax_w2)

    # VP: OBV-Price Correlation
    ax_v = fig.add_subplot(gs[4, 2])
    ax_v.plot(d["start_time"], d["v_obv_corr"].fill_null(0), color=C["purple"], linewidth=1.2)
    ax_v.axhline(0, color=C["gray"], linewidth=0.5)
    ax_v.axhline(-0.3, color=C["green"], linestyle="--", linewidth=0.5, alpha=0.4)
    ax_v.set_title("OBV-Price Correlation")
    fmt_date_axis(ax_v)

    # SM: CPI vs Taker with divergence shade
    ax_s = fig.add_subplot(gs[4, 3])
    ax_s.plot(d["start_time"], d["s_cpi_z"].fill_null(0), color=C["green"], linewidth=1.0, label="CPI Z")
    ax_s.plot(d["start_time"], d["s_taker_z"].fill_null(0), color=C["orange"], linewidth=1.0, label="Taker Z")
    ax_s.axhline(0, color=C["gray"], linewidth=0.5)
    ax_s.set_title("CPI Z vs Taker Z")
    ax_s.legend(fontsize=6)
    fmt_date_axis(ax_s)

    # Decision Box
    ax_d = fig.add_subplot(gs[4, 4])
    _draw_decision_box(ax_d, act)

    fig.savefig(f"{OUT_DIR}/integrated_dashboard.png", bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    print(f"Dashboard: {OUT_DIR}/integrated_dashboard.png")


def _draw_legend_bar(ax, overall):
    ax.axis("off")
    ranges = [
        (-6, -3, "SELL", C["red"], "Trade: hedge/exit\nHODL: reduce 30-50%"),
        (-3, -1, "CAUTION", "#ff6b6b", "Trade: reduce risk\nHODL: pause DCA"),
        (-1, 1, "WAIT", C["gray"], "Trade: stay out\nHODL: do nothing"),
        (1, 3, "WATCH", "#4ecdc4", "Trade: consider entry\nHODL: normal DCA"),
        (3, 6, "BUY", C["green"], "Trade: follow trend\nHODL: add (DCA more)"),
    ]
    bar_y = 0.8
    total = 12.0
    x_start = 0.0
    for low, high, label, color, desc in ranges:
        width = (high - low) / total * 0.9
        rect = mpatches.FancyBboxPatch((x_start, bar_y - 0.18), width, 0.36,
                                        boxstyle="round,pad=0.02", fc=color, ec="white", lw=1, alpha=0.85)
        ax.add_patch(rect)
        if abs(overall) >= abs(low) and abs(overall) <= abs(high) or (overall > low and overall <= high):
            marker_x = x_start + (overall - low) / (high - low) * width
            ax.plot(marker_x, bar_y - 0.3, "v", color=color, markersize=10, markeredgecolor="white", markeredgewidth=1)
            ax.text(marker_x, bar_y - 0.45, f"{overall:+.1f}", fontsize=10, fontweight="bold",
                    ha="center", va="top", color=color)
        ax.text(x_start + width / 2, bar_y + 0.28, label, fontsize=6, fontweight="bold",
                ha="center", va="bottom", color=color)
        ax.text(x_start + width / 2, bar_y - 0.45, desc, fontsize=5,
                ha="center", va="top", color=C["subtext"], alpha=0.8)
        x_start += width + 0.005

    ax.text(x_start + 0.02, bar_y, "Score Range → Action Guide", fontsize=8, color=C["subtext"],
            ha="left", va="center", fontstyle="italic")
    ax.set_xlim(0, 1.05)
    ax.set_ylim(0, 1)


def _draw_score_table(ax, s, act):
    ax.axis("off")
    rows = [
        ("Overall Score", f"{s['overall']:+.1f}", C["green"] if s["overall"] > 0 else C["red"]),
        ("", "", ""),
        ("Whale Flow", f"{s['w_norm']:+.1f}", C["green"] if s["w_norm"] > 0 else C["red"]),
        ("Vol/Price", f"{s['v_norm']:+.1f}", C["green"] if s["v_norm"] > 0 else C["red"]),
        ("Smart Money", f"{s['s_norm']:+.1f}", C["green"] if s["s_norm"] > 0 else C["red"]),
        ("", "", ""),
        ("BTC Price", f"${s['close']:,.0f}" if s['close'] else "N/A", C["text"]),
        ("", "", ""),
        ("Trade Action", act["action"], C["text"]),
        ("HODL Action", act["lth"], C["teal"]),
    ]
    for i, (label, val, color) in enumerate(rows):
        y = 0.95 - i * 0.09
        if label == "":
            continue
        ax.text(0.05, y, label, fontsize=9, ha="left", va="center", color=C["subtext"])
        ax.text(0.95, y, val, fontsize=11 if "Score" in label or "Action" in label else 9,
                ha="right", va="center", color=color, fontweight="bold" if "Score" in label or "Action" in label else "normal")
    ax.set_xlim(0, 1)


def _draw_decision_box(ax, act):
    ax.axis("off")
    box = mpatches.FancyBboxPatch((0.05, 0.05), 0.9, 0.9, boxstyle="round,pad=0.1",
                                   fc=C["panel"], ec=C["grid"], lw=1.5, alpha=0.9)
    ax.add_patch(box)
    ax.text(0.5, 0.82, "TRADE", fontsize=8, ha="center", va="center", color=C["subtext"])
    action_color = C["green"] if "BUY" in act["light"] or "WATCH" in act["light"] else (
        C["red"] if "SELL" in act["light"] or "CAUTION" in act["light"] else C["subtext"])
    ax.text(0.5, 0.64, act["light"], fontsize=13, ha="center", va="center", color=action_color, fontweight="bold")
    ax.text(0.5, 0.47, act["action"], fontsize=7, ha="center", va="center", color=C["text"])
    ax.text(0.5, 0.32, "HODL", fontsize=8, ha="center", va="center", color=C["subtext"])
    ax.text(0.5, 0.18, act["lth"], fontsize=10, ha="center", va="center", color=C["teal"], fontweight="bold")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


def _gauge(ax, val, title):
    v = float(val) if val is not None else 0.0
    v = max(-3, min(3, v))
    theta = np.linspace(np.pi, 0, 120)
    ax.plot(np.cos(theta), np.sin(theta), color=C["grid"], linewidth=3, alpha=0.5)
    # Segmented arc coloring
    for t_low, t_high, color in [(-3, -1, C["red"]), (-1, 1, C["gray"]), (1, 3, C["green"])]:
        seg_theta = np.linspace(np.pi * (1 - (t_high + 3) / 6), np.pi * (1 - (t_low + 3) / 6), 40)
        ax.plot(np.cos(seg_theta), np.sin(seg_theta), color=color, linewidth=4, alpha=0.7)

    needle = np.pi * (1 - (v + 3) / 6)
    ax.arrow(0, 0, 0.7 * np.cos(needle), 0.7 * np.sin(needle),
             head_width=0.08, head_length=0.08,
             fc=C["green"] if v > 0 else C["red"], ec="white", linewidth=0.5)

    for tick in [-3, -2, -1, 0, 1, 2, 3]:
        a = np.pi * (1 - (tick + 3) / 6)
        ax.text(1.15 * np.cos(a), 1.15 * np.sin(a), str(tick), fontsize=6,
                ha="center", va="center", color=C["subtext"])

    ax.text(0, -0.12, f"{v:+.1f}", fontsize=18, fontweight="bold", ha="center", va="center",
            color=C["green"] if v > 0 else (C["red"] if v < 0 else C["subtext"]))
    ax.set_title(title, fontsize=10, fontweight="bold", color=C["text"])
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-0.3, 1.4)
    ax.set_aspect("equal")
    ax.axis("off")


def report(df, s):
    act = score_to_action(s["overall"], s["w_norm"], s["v_norm"], s["s_norm"])
    print(f"""
  ╔══════════════════════════════════════════════╗
  ║  BTC QUANT DASHBOARD    {s['date'][:10]}           ║
  ╠══════════════════════════════════════════════╣
  ║  BTC: ${s['close']:>12,.0f}                          ║
  ║  Trade: {act['light']:<36s} ║
  ║  HODL:  {act['lth']:<36s} ║
  ║                                               ║
  ║  Overall: {s['overall']:+6.1f}    Whale: {s['w_norm']:+6.1f}    VP: {s['v_norm']:+6.1f}    SM: {s['s_norm']:+6.1f}  ║
  ║                                               ║
  ║  {act['summary']:<43s} ║
  ╚══════════════════════════════════════════════╝
""")
    df.tail(365).write_csv(os.path.join(os.path.dirname(__file__), "dashboard_signals.csv"))


def main():
    apply_style()
    print("Loading...")
    dfs = load_module_signals()
    df = align(dfs)
    s = summary(df)
    report(df, s)
    plot_dashboard(df, s)


if __name__ == "__main__":
    main()
