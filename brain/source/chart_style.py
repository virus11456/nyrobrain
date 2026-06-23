import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np

COLORS = {
    "bg": "#0e1117",
    "panel": "#161b22",
    "text": "#c9d1d9",
    "subtext": "#8b949e",
    "green": "#3fb950",
    "red": "#f85149",
    "blue": "#58a6ff",
    "orange": "#d2991d",
    "purple": "#a371f7",
    "teal": "#39d353",
    "yellow": "#e3b341",
    "grid": "#21262d",
    "line": "#30363d",
    "pink": "#db61a2",
    "navy": "#1f6feb",
    "gray": "#484f58",
}

LIGHT = {
    "bg": "#ffffff",
    "panel": "#f6f8fa",
    "text": "#24292f",
    "subtext": "#57606a",
    "green": "#1a7f37",
    "red": "#cf222e",
    "blue": "#0969da",
    "orange": "#9a6700",
    "purple": "#8250df",
    "teal": "#1b7c83",
    "yellow": "#bf8700",
    "grid": "#d0d7de",
    "line": "#afb8c1",
    "pink": "#bf3989",
    "navy": "#0550ae",
    "gray": "#6e7781",
}


def apply_style(dark: bool = False):
    colors = COLORS if dark else LIGHT
    bg = colors["bg"]
    text = colors["text"]
    grid = colors["grid"]

    plt.rcParams.update({
        "figure.facecolor": bg,
        "axes.facecolor": colors["panel"],
        "axes.edgecolor": grid,
        "axes.labelcolor": text,
        "axes.titlecolor": text,
        "text.color": text,
        "xtick.color": text,
        "ytick.color": text,
        "grid.color": grid,
        "grid.alpha": 0.5,
        "grid.linewidth": 0.5,
        "figure.dpi": 150,
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "legend.framealpha": 0.8,
        "legend.facecolor": colors["panel"],
        "legend.edgecolor": grid,
        "lines.linewidth": 1.0,
    })
    return colors


def fmt_date_axis(ax, fmt: str = "%b"):
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    for label in ax.get_xticklabels():
        label.set_rotation(0)


def fmt_date_axis_short(ax, fmt: str = "%b %d"):
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    for label in ax.get_xticklabels():
        label.set_rotation(30, ha="right")


def fmt_currency(ax, currency: str = "$"):
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f"{currency}{x:,.0f}" if abs(x) < 1000 else f"{currency}{x/1000:.0f}k"))
    ax.yaxis.set_major_locator(mticker.MaxNLocator(6))


def fmt_millions(ax):
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f"{x/1e6:.0f}M" if abs(x) >= 1e6 else f"{x:,.0f}"))


def fmt_billions(ax):
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f"{x/1e9:.1f}B" if abs(x) >= 1e9 else f"{x/1e6:.0f}M"))


def smooth_gradient(values, window: int = 5):
    series = np.array(values, dtype=float)
    kernel = np.ones(window) / window
    return np.convolve(series, kernel, mode="same")


def add_signal_bar(ax, dates, values, threshold: float = 0):
    colors = []
    for v in values:
        if v is None or np.isnan(v):
            colors.append("gray")
        elif v > 0:
            colors.append(COLORS["green"] if threshold >= 0 else LIGHT["green"])
        else:
            colors.append(COLORS["red"] if threshold >= 0 else LIGHT["red"])
    ax.bar(dates, values, color=colors, alpha=0.7, width=1.2)
    ax.axhline(threshold, color=COLORS["gray"], linewidth=0.5)


def get_colors():
    return LIGHT
