import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from chart_style import apply_style, fmt_date_axis, fmt_date_axis_short, get_colors
import matplotlib.pyplot as plt

from analyzer import load_ohlcv, compute_signals, latest_summary

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "assets")
C = get_colors()


def plot_vp_dashboard(df, summary):
    os.makedirs(OUT_DIR, exist_ok=True)
    last_date = df["start_time"].tail(1).to_list()[0]
    d = df.filter(df["start_time"] >= last_date - np.timedelta64(365, "D")).sort("start_time")
    m = summary["metrics"]

    fig = plt.figure(figsize=(18, 14))
    gs = fig.add_gridspec(4, 3, height_ratios=[0.7, 2.2, 2.2, 2.2],
                          hspace=0.45, wspace=0.35,
                          left=0.05, right=0.97, top=0.94, bottom=0.05)

    # HEADER
    h = fig.add_subplot(gs[0, :])
    score = summary["signal_score"]
    h.text(0.5, 0.75, "BTC Volume-Price Divergence Monitor",
           fontsize=16, fontweight="bold", ha="center", va="center", color=C["text"])
    h.text(0.5, 0.40,
           f"{summary['status']}  |  Score: {score:+.1f}  |  Momentum: {summary['momentum']:+.1f} ({summary['trend']})",
           fontsize=11, ha="center", va="center",
           color=C["green"] if score > 0 else (C["red"] if score < 0 else C["subtext"]))
    h.text(0.5, 0.15, f"${m['close']:,.0f}  |  Vol: {m['volume']:,.0f} BTC  |  5d/20d Vol: {m['vol_5d_ma']:,.0f}/{m['vol_20d_ma']:,.0f}",
           fontsize=9, ha="center", va="center", color=C["subtext"])
    h.axis("off")

    # ROW 1: Price + Volume
    ax1 = fig.add_subplot(gs[1, :])
    ax1b = ax1.twinx()
    ax1b.plot(d["start_time"], d["close"], color=C["navy"], linewidth=1.5, label="Close price")
    ax1b.fill_between(d["start_time"], d["close"], alpha=0.1, color=C["blue"])
    ax1b.set_ylabel("Price (USD)", color=C["navy"])
    ax1b.tick_params(axis="y", colors=C["navy"])
    c_vol = [C["green"] if c > o else C["red"] for c, o in zip(d["close"], d["open"])]
    ax1.bar(d["start_time"], d["volume"], color=c_vol, alpha=0.35, width=1.2)
    ax1.set_ylabel("Volume (BTC)")
    ax1.set_title("Daily Price & Volume", fontweight="bold")
    fmt_date_axis(ax1)

    # ROW 2: Volume MAs
    ax2 = fig.add_subplot(gs[2, 0])
    ax2.fill_between(d["start_time"], d["vol_5d_ma"].fill_null(0), alpha=0.3, color=C["blue"], label="5d MA")
    ax2.plot(d["start_time"], d["vol_20d_ma"].fill_null(0), color=C["navy"], linewidth=1.2, label="20d MA")
    ax2.plot(d["start_time"], d["vol_50d_ma"].fill_null(0), color=C["gray"], linewidth=0.8, linestyle="--", label="50d MA")
    ax2.set_ylabel("Volume (BTC)")
    ax2.set_title("Volume Moving Averages", fontweight="bold")
    ax2.legend(fontsize=7)
    fmt_date_axis(ax2)

    # ROW 2: OBV-Price Correlation
    ax3 = fig.add_subplot(gs[2, 1])
    corr = d["obv_price_corr_30d"].fill_null(0)
    ax3.fill_between(d["start_time"], 0, corr, alpha=0.2,
                     color=[C["green"] if v < -0.3 else (C["red"] if v > 0.5 else C["gray"]) for v in corr])
    ax3.plot(d["start_time"], corr, color=C["purple"], linewidth=1.2)
    ax3.axhline(0, color=C["gray"], linewidth=0.5)
    ax3.axhline(-0.5, color=C["green"], linestyle="--", linewidth=0.5, alpha=0.5, label="Bullish div")
    ax3.axhline(0.5, color=C["red"], linestyle="--", linewidth=0.5, alpha=0.5, label="Bearish conf")
    ax3.set_ylabel("Correlation")
    ax3.set_title("OBV-Price 30d Rolling Correlation\n(negative = bullish divergence)", fontweight="bold")
    ax3.legend(fontsize=6)
    fmt_date_axis(ax3)

    # ROW 2: Volume Z-Score
    ax4 = fig.add_subplot(gs[2, 2])
    zs = d["vol_zscore_90d"].fill_null(0)
    c_z = [C["red"] if v > 1.5 else (C["green"] if v < -1.5 else (C["orange"] if v > 0 else C["teal"])) for v in zs]
    ax4.bar(d["start_time"], zs, color=c_z, alpha=0.6, width=1.2)
    ax4.axhline(0, color=C["gray"], linewidth=0.5)
    ax4.axhline(1.5, color=C["red"], linestyle="--", linewidth=0.5, alpha=0.4)
    ax4.axhline(-1.5, color=C["green"], linestyle="--", linewidth=0.5, alpha=0.4)
    ax4.set_ylabel("Z-Score")
    ax4.set_title("Volume Z-Score (90d baseline)\n(extreme high = climax, extreme low = bottom)", fontweight="bold")
    fmt_date_axis(ax4)

    # ROW 3: OBV vs Price
    ax5 = fig.add_subplot(gs[3, 0])
    ax5b = ax5.twinx()
    ax5b.plot(d["start_time"], d["close"], color=C["gray"], alpha=0.35, linewidth=0.8)
    ax5b.set_ylabel("Price", color=C["gray"])
    ax5b.tick_params(axis="y", colors=C["gray"])
    ax5.plot(d["start_time"], d["obv"].fill_null(0) / 1e6, color=C["purple"], linewidth=1.2)
    ax5.set_ylabel("OBV (Millions)")
    ax5.set_title("On-Balance Volume vs Price", fontweight="bold")
    fmt_date_axis(ax5)

    # ROW 3: Price-Volume Alignment
    ax6 = fig.add_subplot(gs[3, 1])
    vs = df["vp_signal"].fill_null(0)
    c_v = [C["green"] if v > 0.3 else (C["red"] if v < -0.3 else C["gray"]) for v in vs]
    ax6.bar(df["start_time"], vs, color=c_v, alpha=0.7, width=1.2)
    ax6.axhline(0, color=C["gray"], linewidth=0.5)
    ax6.set_ylabel("Bearish <--> Bullish")
    ax6.set_title("Composite VP Signal", fontweight="bold")
    ax6.set_ylim(-3, 3)
    fmt_date_axis(ax6)

    # ROW 3: Scatter Volume vs Price (last 90d)
    ax7 = fig.add_subplot(gs[3, 2])
    d90 = d.tail(90)
    avg_close = d90["close"].mean()
    c_scatter = [C["red"] if v > avg_close else C["blue"] for v in d90["close"]]
    ax7.scatter(d90["close"], d90["volume"], c=c_scatter, alpha=0.5, s=12)
    z = np.polyfit(d90["close"].to_numpy(), d90["volume"].to_numpy(), 1)
    xs = np.linspace(d90["close"].min(), d90["close"].max(), 50)
    ax7.plot(xs, np.poly1d(z)(xs), color=C["gray"], linestyle="--", linewidth=0.8, alpha=0.6)
    ax7.set_xlabel("Close Price (USD)")
    ax7.set_ylabel("Volume (BTC)")
    ax7.set_title("Volume vs Price Scatter (90d)\n(red = above avg px, blue = below)", fontweight="bold")

    fig.savefig(f"{OUT_DIR}/vp_dashboard.png", bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    print(f"Dashboard: {OUT_DIR}/vp_dashboard.png")


def main():
    apply_style()
    print("Loading OHLCV...")
    df = load_ohlcv(DATA_DIR)
    print("Computing VP signals...")
    df = compute_signals(df)
    summary = latest_summary(df)

    print(f"\n{'='*55}")
    print(f"  BTC Volume-Price Divergence  |  {summary['status']}")
    print(f"  Score: {summary['signal_score']:+.2f}  |  Momentum: {summary['momentum']:+.2f} ({summary['trend']})")
    print(f"  Vol-Price: {summary['vol_price_desc']}")
    print(f"  OBV: {summary['obv_desc']}")
    m = summary["metrics"]
    print(f"  Close: ${m['close']:,.0f}  |  Vol: {m['volume']:,.0f} BTC")
    print(f"{'='*55}\n")

    plot_vp_dashboard(df, summary)
    df.tail(365).write_csv(os.path.join(os.path.dirname(__file__), "vp_signals.csv"))


if __name__ == "__main__":
    main()
