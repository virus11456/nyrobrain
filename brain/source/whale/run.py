import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from chart_style import apply_style, fmt_date_axis, fmt_date_axis_short, get_colors
import matplotlib.pyplot as plt

from analyzer import load_data, compute_signals, latest_summary

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "assets")
C = get_colors()


def plot_whale_dashboard(df, summary):
    os.makedirs(OUT_DIR, exist_ok=True)
    last_date = df["start_time"].tail(1).to_list()[0]
    lookback = last_date - np.timedelta64(365, "D")
    d = df.filter(df["start_time"] >= lookback).sort("start_time")
    m = summary["metrics"]

    fig = plt.figure(figsize=(18, 14))
    gs = fig.add_gridspec(4, 3, height_ratios=[0.8, 2.5, 2.5, 2.5],
                          hspace=0.45, wspace=0.35,
                          left=0.05, right=0.97, top=0.94, bottom=0.05)

    # ── HEADER ──
    h = fig.add_subplot(gs[0, :])
    score = summary["score"]
    h.text(0.5, 0.75, f"BTC Whale Accumulation Monitor",
           fontsize=16, fontweight="bold", ha="center", va="center", color=C["text"])
    h.text(0.5, 0.40,
           f"{summary['status']}  |  Score: {score:+.1f}  |  Momentum: {summary['momentum']:+.1f} ({summary['trend']})",
           fontsize=11, ha="center", va="center",
           color=C["green"] if score > 0 else (C["red"] if score < 0 else C["subtext"]))
    h.text(0.5, 0.15, f"Reserve: {m['reserve_btc']:,.0f} BTC  |  Netflow 7d: {m['netflow_7d_sum']:+,.0f} BTC",
           fontsize=9, ha="center", va="center", color=C["subtext"])
    h.axis("off")

    # ── ROW 1: Exchange Reserve + Netflow ──
    ax1 = fig.add_subplot(gs[1, 0])
    ax1b = ax1.twinx()
    ax1b.plot(d["start_time"], d["reserve"] / 1e6, color=C["blue"], linewidth=1.5, label="Reserve (M BTC)")
    ax1b.set_ylabel("Reserve (M BTC)", color=C["blue"])
    ax1b.tick_params(axis="y", colors=C["blue"])
    c_flow = [C["green"] if v < 0 else C["red"] for v in d["netflow_7d_sum"].fill_null(0)]
    ax1.bar(d["start_time"], d["netflow_7d_sum"].fill_null(0), color=c_flow, alpha=0.5, width=1.2)
    ax1.set_ylabel("7d Netflow (BTC)")
    ax1.axhline(0, color=C["gray"], linewidth=0.5)
    ax1.set_title("Exchange Reserve & 7d Netflow", fontweight="bold")
    fmt_date_axis(ax1)

    # ── ROW 1: Reserve Z-Score ──
    ax2 = fig.add_subplot(gs[1, 1])
    zs = d["reserve_zscore"].fill_null(0)
    ax2.fill_between(d["start_time"], 0, zs, alpha=0.3,
                     color=[C["green"] if v < 0 else C["red"] for v in zs])
    ax2.plot(d["start_time"], zs, color=C["blue"], linewidth=1.2)
    ax2.axhline(0, color=C["gray"], linewidth=0.5)
    ax2.axhline(-1, color=C["green"], linestyle="--", linewidth=0.5, alpha=0.6)
    ax2.axhline(1, color=C["red"], linestyle="--", linewidth=0.5, alpha=0.6)
    ax2.set_ylabel("Z-Score")
    ax2.set_title("Exchange Reserve Z-Score\n(↓ = accumulation)", fontweight="bold")
    fmt_date_axis(ax2)

    # ── ROW 1: Stablecoin Reserve ──
    ax3 = fig.add_subplot(gs[1, 2])
    sr = d["stable_reserve"].fill_null(0) / 1e9
    ax3.fill_between(d["start_time"], sr, alpha=0.4, color=C["teal"])
    ax3.plot(d["start_time"], sr, color=C["teal"], linewidth=1.2)
    ax3.set_ylabel("USDT/USDC ($B)")
    ax3.set_title("Stablecoin Reserve on Exchanges\n(↑ = buying power building)", fontweight="bold")
    fmt_date_axis(ax3)

    # ── ROW 2: Whale Ratio + FFR ──
    ax4 = fig.add_subplot(gs[2, 0])
    ax4.plot(d["start_time"], d["exchange_whale_ratio"] * 100, color=C["orange"], linewidth=1.2, label="Whale Ratio %")
    ax4.plot(d["start_time"], d["whale_ratio_30d_ma"] * 100, color=C["yellow"], linewidth=0.8,
             linestyle="--", label="30d MA")
    ax4.axhline(d["exchange_whale_ratio"].mean() * 100, color=C["gray"], linestyle=":", linewidth=0.5)
    ax4.set_ylabel("% of Inflow")
    ax4.set_title("Exchange Whale Ratio\n(↓ = less whale selling)", fontweight="bold")
    ax4.legend(fontsize=7)
    fmt_date_axis(ax4)

    # ── ROW 2: Fund Flow Ratio ──
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.plot(d["start_time"], d["fund_flow_ratio"] * 100, color=C["purple"], linewidth=1.2, label="FFR %")
    ax5.plot(d["start_time"], d["ffr_30d_ma"] * 100, color=C["pink"], linewidth=0.8, linestyle="--", label="30d MA")
    ax5.set_ylabel("% of On-Chain Vol")
    ax5.set_title("Fund Flow Ratio\n(↓ = less flow to exchanges)", fontweight="bold")
    ax5.legend(fontsize=7)
    fmt_date_axis(ax5)

    # ── ROW 2: MPI ──
    ax6 = fig.add_subplot(gs[2, 2])
    ax6.plot(d["start_time"], d["mpi"], color=C["red"], linewidth=1.2, label="MPI")
    ax6.plot(d["start_time"], d["mpi_30d_ma"], color=C["orange"], linewidth=0.8, linestyle="--", label="30d MA")
    ax6.axhline(2.0, color=C["red"], linestyle=":", linewidth=0.6, alpha=0.6, label="Sell threshold")
    ax6.set_ylabel("MPI")
    ax6.set_title("Miner Position Index\n(>2 = miners overselling)", fontweight="bold")
    ax6.legend(fontsize=7)
    fmt_date_axis(ax6)

    # ── ROW 3: Individual Signal Bars ──
    ax7 = fig.add_subplot(gs[3, 0])
    _plot_signal_bars(ax7, d, "sig_reserve", C["blue"], "Reserve Signal")
    fmt_date_axis(ax7)

    ax8 = fig.add_subplot(gs[3, 1])
    _plot_signal_bars(ax8, d, "sig_netflow", C["teal"], "Netflow Signal")
    fmt_date_axis(ax8)

    ax9 = fig.add_subplot(gs[3, 2])
    cs = d["composite_whale_score"].fill_null(0)
    c_bar = [C["green"] if v > 0 else (C["red"] if v < 0 else C["gray"]) for v in cs]
    ax9.bar(d["start_time"], cs, color=c_bar, alpha=0.8, width=1.2)
    ax9.axhline(0, color=C["gray"], linewidth=0.5)
    ax9.set_ylabel("Accum <--> Dist")
    ax9.set_title("Composite Whale Score", fontweight="bold")
    ax9.set_ylim(-5, 5)
    fmt_date_axis(ax9)

    fig.savefig(f"{OUT_DIR}/whale_dashboard.png", bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    print(f"Dashboard: {OUT_DIR}/whale_dashboard.png")


def _plot_signal_bars(ax, d, col, color, title):
    vals = d[col].fill_null(0)
    c_bar = [C["green"] if v > 0.2 else (C["red"] if v < -0.2 else C["gray"]) for v in vals]
    ax.bar(d["start_time"], vals, color=c_bar, alpha=0.7, width=1.2)
    ax.axhline(0, color=C["gray"], linewidth=0.5)
    ax.axhline(0.3, color=C["green"], linestyle=":", linewidth=0.5, alpha=0.4)
    ax.axhline(-0.3, color=C["red"], linestyle=":", linewidth=0.5, alpha=0.4)
    ax.set_ylabel("Signal [-2,+2]")
    ax.set_title(title, fontweight="bold")
    ax.set_ylim(-2.5, 2.5)


def main():
    apply_style()
    print("Loading data...")
    data = load_data(DATA_DIR)
    print("Computing signals...")
    df = compute_signals(data)
    summary = latest_summary(df)

    print(f"\n{'='*55}")
    print(f"  BTC Whale Monitor  |  {summary['status']}")
    print(f"  Score: {summary['score']:+.2f}  |  Momentum: {summary['momentum']:+.2f} ({summary['trend']})")
    print(f"  {summary['detail']}")
    print(f"\n  Signals:")
    sig_map = {
        "Reserve": "sig_reserve", "Netflow": "sig_netflow",
        "Whale Ratio": "sig_whale", "Stablecoin": "sig_stable",
        "Fund Flow": "sig_ffr", "MPI": "sig_mpi",
    }
    for label, key in sig_map.items():
        v = summary["metrics"].get(key)
        if v is not None:
            bar = "++" if v > 0.5 else ("+" if v > 0.2 else ("--" if v < -0.5 else ("-" if v < -0.2 else " .")))
            print(f"    [{bar}] {label:12s} {v:+8.3f}")
    print(f"{'='*55}\n")

    plot_whale_dashboard(df, summary)
    df.tail(365).write_csv(os.path.join(os.path.dirname(__file__), "whale_signals.csv"))


if __name__ == "__main__":
    main()
