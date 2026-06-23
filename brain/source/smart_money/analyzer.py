import polars as pl
import numpy as np


def load_data(data_dir: str) -> dict[str, pl.DataFrame]:
    names = ["taker", "coinbase_premium", "funding", "oi", "price_spot"]
    data = {}
    for name in names:
        path = f"{data_dir}/{name}.parquet"
        try:
            df = pl.read_parquet(path).sort("start_time").unique(subset=["start_time"])
            data[name] = df
        except FileNotFoundError:
            print(f"WARN: missing {path}")
    return data


def _zscore(col: pl.Expr, window: int = 365) -> pl.Expr:
    return (col - col.rolling_mean(window, min_periods=60)) / col.rolling_std(window, min_periods=60)


def _tanh_squash(x: pl.Expr, scale: float = 1.5) -> pl.Expr:
    return (x / scale).tanh() * 2.0


def compute_signals(data: dict[str, pl.DataFrame]) -> pl.DataFrame:
    # ---- 1. Coinbase Premium Index ----
    cp = data["coinbase_premium"].select([
        "start_time", "coinbase_premium_index"
    ])
    cp = cp.with_columns([
        pl.col("coinbase_premium_index").rolling_mean(7).alias("cpi_7d_ma"),
        pl.col("coinbase_premium_index").rolling_mean(30).alias("cpi_30d_ma"),
        _zscore(pl.col("coinbase_premium_index"), 365).alias("cpi_zscore"),
    ])
    # Positive CPI = institutional buying. Use continuous score.
    cp = cp.with_columns([
        _tanh_squash(pl.col("cpi_zscore"), 1.5).alias("sig_cpi"),
    ])

    # ---- 2. Taker Buy/Sell ----
    tk = data["taker"].select([
        "start_time", "taker_buy_sell_ratio", "taker_buy_volume", "taker_sell_volume"
    ])
    tk = tk.with_columns([
        (pl.col("taker_buy_volume") - pl.col("taker_sell_volume")).alias("taker_net_volume"),
    ])
    tk = tk.with_columns([
        pl.col("taker_buy_sell_ratio").rolling_mean(7).alias("tbsr_7d_ma"),
        pl.col("taker_buy_sell_ratio").rolling_mean(30).alias("tbsr_30d_ma"),
        _zscore(pl.col("taker_buy_sell_ratio"), 365).alias("tbsr_zscore"),
        pl.col("taker_net_volume").rolling_sum(7).alias("taker_net_7d_sum"),
    ])
    tk = tk.with_columns([
        _tanh_squash(pl.col("tbsr_zscore"), 1.5).alias("sig_taker"),
    ])

    # ---- 3. Funding Rate ----
    fr = data["funding"].select(["start_time", "funding_rates"])
    fr = fr.with_columns([
        pl.col("funding_rates").rolling_mean(7).alias("funding_7d_ma"),
        _zscore(pl.col("funding_rates"), 365).alias("funding_zscore"),
    ])
    # Funding: moderate positive = healthy bullish, extreme positive (z > 2) = crowded longs (bearish)
    # Negative funding (z < -1) = shorts dominant (potentially bullish squeeze setup)
    fr = fr.with_columns([
        pl.when(pl.col("funding_zscore") > 2.0).then(-pl.col("funding_zscore") / 2.0)
        .when(pl.col("funding_zscore") < -1.0).then(-pl.col("funding_zscore") / 2.0)
        .otherwise(pl.col("funding_zscore") * 0.3)
        .alias("sig_funding_raw"),
    ])
    fr = fr.with_columns([
        _tanh_squash(pl.col("sig_funding_raw"), 1.5).alias("sig_funding"),
    ])

    # ---- 4. Open Interest-Price Divergence ----
    oi = data["oi"].select(["start_time", "open_interest"]).rename({"open_interest": "oi"})
    px = data["price_spot"].select(["start_time", "close"])

    oi_px = oi.join(px, on="start_time", how="inner")
    oi_px = oi_px.with_columns([
        pl.col("oi").pct_change(7).alias("oi_7d_chg"),
        pl.col("oi").pct_change(30).alias("oi_30d_chg"),
        pl.col("close").pct_change(7).alias("px_7d_chg"),
        pl.col("close").pct_change(30).alias("px_30d_chg"),
    ])
    # OI-Price divergence metric: OI change minus price change
    oi_px = oi_px.with_columns([
        (pl.col("oi_7d_chg") - pl.col("px_7d_chg")).alias("oi_px_div_7d"),
        (pl.col("oi_30d_chg") - pl.col("px_30d_chg")).alias("oi_px_div_30d"),
    ])
    # Signal: price falling + OI rising = bearish positioning (shorts building)
    # Price rising + OI rising = bullish positioning
    # Price falling + OI falling = capitulation / forced liquidation (bullish medium term)
    oi_px = oi_px.with_columns([
        pl.when((pl.col("px_7d_chg") < -0.02) & (pl.col("oi_7d_chg") > 0.02)).then(-1.5)
        .when((pl.col("px_7d_chg") > 0.02) & (pl.col("oi_7d_chg") > 0.02)).then(1.0)
        .when((pl.col("px_7d_chg") < -0.05) & (pl.col("oi_7d_chg") < -0.05)).then(1.5)  # capitulation
        .otherwise(0.0)
        .alias("sig_oi_div"),
    ])

    # ---- 5. CPI-Taker Divergence ----
    # When institutions selling (CPI neg) but retail aggressively buying (taker high),
    # this is a distribution signal (smart money selling to retail)

    # ---- Join everything ----
    all_times = pl.concat([
        cp.select("start_time"), tk.select("start_time"),
        fr.select("start_time"), oi_px.select("start_time"),
    ]).unique().sort("start_time")

    joined = (all_times
        .join(cp, on="start_time", how="left")
        .join(tk, on="start_time", how="left")
        .join(fr, on="start_time", how="left")
        .join(oi_px, on="start_time", how="left")
    )

    # CPI-Taker Divergence Flag
    joined = joined.with_columns([
        pl.when(
            (pl.col("cpi_zscore") < -1.0) & (pl.col("tbsr_zscore") > 1.0)
        ).then(-1.0)  # strong divergence: insti selling, retail buying
        .when(
            (pl.col("cpi_zscore") > 1.0) & (pl.col("tbsr_zscore") < -1.0)
        ).then(1.0)  # insti buying, retail selling
        .otherwise(0.0)
        .alias("sig_cpi_taker_div"),
    ])

    # ---- Composite Smart Money Score ----
    # weights: CPI=0.30, Taker=0.25, Funding=0.15, OI=0.20, Divergence=0.10
    joined = joined.with_columns([
        (pl.col("sig_cpi").fill_null(0) * 0.30
         + pl.col("sig_taker").fill_null(0) * 0.25
         + pl.col("sig_funding").fill_null(0) * 0.15
         + pl.col("sig_oi_div").fill_null(0) * 0.20
         + pl.col("sig_cpi_taker_div").fill_null(0) * 0.10)
        .alias("composite_sm_score"),
    ])

    # Signal momentum
    joined = joined.with_columns([
        (pl.col("composite_sm_score") - pl.col("composite_sm_score").shift(7)).alias("sm_momentum"),
    ])

    return joined


def latest_summary(df: pl.DataFrame) -> dict:
    row = df.tail(1).to_dicts()[0]
    score = row.get("composite_sm_score", 0) or 0
    momentum = row.get("sm_momentum", 0) or 0
    cpi_z = row.get("cpi_zscore")
    tbsr_z = row.get("tbsr_zscore")
    cpi_taker_div = row.get("sig_cpi_taker_div", 0) or 0

    if score >= 1.5:
        status = "STRONG_SMART_BUYING"
    elif score >= 0.5:
        status = "MODERATE_SMART_BUYING"
    elif score >= -0.5:
        status = "NEUTRAL"
    elif score >= -1.5:
        status = "MODERATE_SMART_SELLING"
    else:
        status = "STRONG_SMART_SELLING"

    if momentum > 0.2:
        trend = "IMPROVING (偏多轉強)"
    elif momentum < -0.2:
        trend = "DETERIORATING (偏空增強)"
    else:
        trend = "STABLE"

    # Sub-component descriptions
    parts = []
    if cpi_z is not None:
        if cpi_z > 0.3:
            parts.append(f"Coinbase溢價偏多 (Z={cpi_z:.1f})")
        elif cpi_z < -0.3:
            parts.append(f"Coinbase折價偏空 (Z={cpi_z:.1f})")
        else:
            parts.append(f"Coinbase中性 (Z={cpi_z:.1f})")

    if tbsr_z is not None:
        if tbsr_z > 0.3:
            parts.append(f"主動買盤強 (Z={tbsr_z:.1f})")
        elif tbsr_z < -0.3:
            parts.append(f"主動賣盤強 (Z={tbsr_z:.1f})")
        else:
            parts.append(f"主動買賣均衡 (Z={tbsr_z:.1f})")

    if cpi_taker_div < -0.5:
        parts.append("警報: 機構賣出 vs 散戶買入 — 派發結構")
    elif cpi_taker_div > 0.5:
        parts.append("機構買入 vs 散戶賣出 — 吸籌結構")

    detail = "; ".join(parts) if parts else "訊號平衡"

    return {
        "date": str(row["start_time"]),
        "status": status,
        "composite_score": round(score, 2),
        "momentum": round(momentum, 2),
        "trend": trend,
        "detail": detail,
        "metrics": {
            "coinbase_premium_index": row.get("coinbase_premium_index"),
            "cpi_zscore": cpi_z,
            "sig_cpi": row.get("sig_cpi"),
            "taker_buy_sell_ratio": row.get("taker_buy_sell_ratio"),
            "tbsr_zscore": tbsr_z,
            "sig_taker": row.get("sig_taker"),
            "taker_net_7d_sum": row.get("taker_net_7d_sum"),
            "funding_rates": row.get("funding_rates"),
            "funding_zscore": row.get("funding_zscore"),
            "sig_funding": row.get("sig_funding"),
            "oi": row.get("oi"),
            "close": row.get("close"),
            "oi_7d_chg": row.get("oi_7d_chg"),
            "px_7d_chg": row.get("px_7d_chg"),
            "sig_oi_div": row.get("sig_oi_div"),
            "sig_cpi_taker_div": row.get("sig_cpi_taker_div"),
        }
    }
