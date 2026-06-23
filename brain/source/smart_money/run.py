import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from chart_style import apply_style, fmt_date_axis, fmt_date_axis_short, get_colors
import matplotlib.pyplot as plt

from analyzer import load_data, compute_signals, latest_summary

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "assets")
C = get_colors()


def plot_sm_dashboard(df, summary):
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
    score = summary["composite_score"]
    h.text(0.5, 0.75, "BTC Smart Money Monitor",
           fontsize=16, fontweight="bold", ha="center", va="center", color=C["text"])
    h.text(0.5, 0.40,
           f"{summary['status']}  |  Score: {score:+.1f}  |  Momentum: {summary['momentum']:+.1f} ({summary['trend']})",
           fontsize=11, ha="center", va="center",
           color=C["green"] if score > 0 else (C["red"] if score < 0 else C["subtext"]))
    h.text(0.5, 0.13,
           f"CPI Z: {m['cpi_zscore']:+.1f}  |  Taker Z: {m['tbsr_zscore']:+.1f}  |  "
           f"Funding Z: {m['funding_zscore']:+.1f}  |  CPI-Taker Div: {m['sig_cpi_taker_div']:+.1f}",
           fontsize=8, ha="center", va="center", color=C["subtext"])
    h.axis("off")

    # ROW 1: Coinbase Premium Index
    ax1 = fig.add_subplot(gs[1, 0])
    cpi = d["coinbase_premium_index"].fill_null(0)
    pos_mask = cpi >= 0
    ax1.fill_between(d["start_time"], 0, cpi, where=pos_mask, color=C["green"], alpha=0.3)
    ax1.fill_between(d["start_time"], 0, cpi, where=~pos_mask, color=C["red"], alpha=0.3)
    ax1.plot(d["start_time"], cpi, color=C["navy"], linewidth=1.0)
    ax1.plot(d["start_time"], d["cpi_7d_ma"].fill_null(0), color=C["green"], linewidth=1.2, label="7d MA")
    ax1.axhline(0, color=C["gray"], linewidth=0.5)
    ax1.set_ylabel("Premium Index")
    ax1.set_title("Coinbase Premium Index\n(green = institutional buying)", fontweight="bold")
    ax1.legend(fontsize=7)
    fmt_date_axis(ax1)

    # ROW 1: Taker Buy/Sell Ratio
    ax2 = fig.add_subplot(gs[1, 1])
    tbsr = d["taker_buy_sell_ratio"].fill_null(1.0)
    pos_mask2 = tbsr >= 1.0
    ax2.fill_between(d["start_time"], 1.0, tbsr, where=pos_mask2, color=C["green"], alpha=0.3)
    ax2.fill_between(d["start_time"], 1.0, tbsr, where=~pos_mask2, color=C["red"], alpha=0.3)
    ax2.plot(d["start_time"], tbsr, color=C["navy"], linewidth=1.0)
    ax2.plot(d["start_time"], d["tbsr_7d_ma"].fill_null(1.0), color=C["orange"], linewidth=1.2, label="7d MA")
    ax2.axhline(1.0, color=C["gray"], linewidth=0.5)
    ax2.set_ylabel("Buy/Sell Ratio")
    ax2.set_title("Taker Buy/Sell Ratio\n(>1 = aggressive buyers dominate)", fontweight="bold")
    ax2.legend(fontsize=7)
    fmt_date_axis(ax2)

    # ROW 1: Funding Rate
    ax3 = fig.add_subplot(gs[1, 2])
    fr = d["funding_rates"].fill_null(0) * 100
    c_fr = [C["red"] if v > 0.01 else (C["green"] if v < 0 else C["gray"]) for v in d["funding_rates"].fill_null(0)]
    ax3.bar(d["start_time"], fr, color=c_fr, alpha=0.5, width=1.2)
    ax3.axhline(0, color=C["gray"], linewidth=0.5)
    ax3.axhline(1.0, color=C["red"], linestyle="--", linewidth=0.5, alpha=0.4, label="crowded longs")
    ax3.set_ylabel("Funding Rate (%)")
    ax3.set_title("Perpetual Funding Rate\n(red > 0.01% = longs crowded)", fontweight="bold")
    ax3.legend(fontsize=7)
    fmt_date_axis(ax3)

    # ROW 2: OI vs Price
    ax4 = fig.add_subplot(gs[2, 0])
    ax4b = ax4.twinx()
    ax4b.plot(d["start_time"], d["close"], color=C["navy"], linewidth=1.2)
    ax4b.set_ylabel("Price (USD)", color=C["navy"])
    ax4b.tick_params(axis="y", colors=C["navy"])
    ax4.plot(d["start_time"], d["oi"].fill_null(0) / 1e9, color=C["purple"], linewidth=1.2)
    ax4.set_ylabel("OI ($B)")
    ax4.set_title("Open Interest vs Price\n(OI rising + px falling = shorts building)", fontweight="bold")
    fmt_date_axis(ax4)

    # ROW 2: CPI Z-Score
    ax5 = fig.add_subplot(gs[2, 1])
    cz = d["cpi_zscore"].fill_null(0)
    ax5.fill_between(d["start_time"], 0, cz, alpha=0.25,
                     color=[C["green"] if v > 0 else C["red"] for v in cz])
    ax5.plot(d["start_time"], cz, color=C["navy"], linewidth=1.2)
    ax5.axhline(0, color=C["gray"], linewidth=0.5)
    ax5.set_ylabel("Z-Score")
    ax5.set_title("CPI Z-Score\n(positive = institutional buying)", fontweight="bold")
    fmt_date_axis(ax5)

    # ROW 2: Taker + CPI Z-Score together (divergence view)
    ax6 = fig.add_subplot(gs[2, 2])
    ax6.plot(d["start_time"], d["cpi_zscore"].fill_null(0), color=C["green"], linewidth=1.2, label="CPI Z")
    ax6.plot(d["start_time"], d["tbsr_zscore"].fill_null(0), color=C["orange"], linewidth=1.2, label="Taker Z")
    ax6.axhline(0, color=C["gray"], linewidth=0.5)
    ax6.set_ylabel("Z-Score")
    ax6.set_title("CPI vs Taker Z-Score\n(divergence = distribution signal)", fontweight="bold")
    ax6.legend(fontsize=7)
    fmt_date_axis(ax6)

    # ROW 3: Taker Net Volume
    ax7 = fig.add_subplot(gs[3, 0])
    tn = d["taker_net_volume"].fill_null(0) / 1e9
    c_tn = [C["green"] if v > 0 else C["red"] for v in d["taker_net_volume"].fill_null(0)]
    ax7.bar(d["start_time"], tn, color=c_tn, alpha=0.5, width=1.2)
    ax7.axhline(0, color=C["gray"], linewidth=0.5)
    ax7.set_ylabel("Net Buy ($B)")
    ax7.set_title("Taker Net Volume (Buy - Sell)\n(green = net buying)", fontweight="bold")
    fmt_date_axis(ax7)

    # ROW 3: OI-Px Divergence
    ax8 = fig.add_subplot(gs[3, 1])
    odv = d["oi_px_div_7d"].fill_null(0) * 100
    c_odv = [C["red"] if v > 0 else C["green"] for v in odv]
    ax8.bar(d["start_time"], odv, color=c_odv, alpha=0.5, width=1.2)
    ax8.axhline(0, color=C["gray"], linewidth=0.5)
    ax8.set_ylabel("OI-Px Diverg. (%)")
    ax8.set_title("OI-Price Divergence (7d)\n(positive = OI outpacing px = hedging)", fontweight="bold")
    fmt_date_axis(ax8)

    # ROW 3: Composite SM Score
    ax9 = fig.add_subplot(gs[3, 2])
    cs = d["composite_sm_score"].fill_null(0)
    c_cs = [C["green"] if v > 0.3 else (C["red"] if v < -0.3 else C["gray"]) for v in cs]
    ax9.bar(d["start_time"], cs, color=c_cs, alpha=0.7, width=1.2)
    ax9.axhline(0, color=C["gray"], linewidth=0.5)
    ax9.set_ylim(-3, 3)
    ax9.set_ylabel("Bearish <--> Bullish")
    ax9.set_title("Composite Smart Money Score", fontweight="bold")
    fmt_date_axis(ax9)

    fig.savefig(f"{OUT_DIR}/smart_money_dashboard.png", bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    print(f"Dashboard: {OUT_DIR}/smart_money_dashboard.png")


def main():
    apply_style()
    print("Loading data...")
    data = load_data(DATA_DIR)
    print("Computing smart money signals...")
    df = compute_signals(data)
    summary = latest_summary(df)

    print(f"\n{'='*55}")
    print(f"  BTC Smart Money  |  {summary['status']}")
    print(f"  Score: {summary['composite_score']:+.2f}  |  Momentum: {summary['momentum']:+.2f} ({summary['trend']})")
    print(f"  {summary['detail']}")
    m = summary["metrics"]
    print(f"  CPI: {m['cpi_zscore']:+.2f}z  |  Taker: {m['tbsr_zscore']:+.2f}z  |  Funding: {m['funding_zscore']:+.2f}z")
    print(f"  OI 7d: {m['oi_7d_chg']*100:+.1f}%  |  Px 7d: {m['px_7d_chg']*100:+.1f}%")
    print(f"  CPI-Taker Div: {m['sig_cpi_taker_div']:+.1f}")
    print(f"{'='*55}\n")

    plot_sm_dashboard(df, summary)
    df.tail(365).write_csv(os.path.join(os.path.dirname(__file__), "smart_money_signals.csv"))


if __name__ == "__main__":
    main()
