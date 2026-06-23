import polars as pl
import numpy as np


def load_data(data_dir: str) -> dict[str, pl.DataFrame]:
    names = ["reserve", "netflow", "whale_ratio", "stable_reserve", "fund_flow_ratio", "mpi"]
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
    return (x / scale).tanh() * 2.0  # maps to roughly [-2, 2]


def compute_signals(data: dict[str, pl.DataFrame]) -> pl.DataFrame:
    # ---- 1. Exchange Reserve ----
    df_r = data["reserve"].select(["start_time", "reserve"])
    df_r = df_r.with_columns([
        pl.col("reserve").pct_change(7).alias("reserve_7d_chg"),
        pl.col("reserve").pct_change(30).alias("reserve_30d_chg"),
        pl.col("reserve").pct_change(90).alias("reserve_90d_chg"),
        _zscore(pl.col("reserve"), 365).alias("reserve_zscore"),
    ])
    # Signal: decreasing reserve = bullish. Z-score inversion so negative z -> positive signal.
    df_r = df_r.with_columns([
        _tanh_squash(-pl.col("reserve_zscore"), 1.5).alias("sig_reserve_raw"),
        # Multi-timeframe alignment bonus
        pl.when(
            (pl.col("reserve_7d_chg") < 0) & (pl.col("reserve_30d_chg") < 0) & (pl.col("reserve_90d_chg") < 0)
        ).then(0.5).when(
            (pl.col("reserve_7d_chg") > 0) & (pl.col("reserve_30d_chg") > 0) & (pl.col("reserve_90d_chg") > 0)
        ).then(-0.5).otherwise(0.0).alias("reserve_align"),
    ])
    df_r = df_r.with_columns([
        (pl.col("sig_reserve_raw") + pl.col("reserve_align")).clip(-2.0, 2.0).alias("sig_reserve"),
    ])

    # ---- 2. Netflow ----
    df_n = data["netflow"].select(["start_time", "netflow_total"])
    df_n = df_n.with_columns([
        pl.col("netflow_total").rolling_sum(7).alias("netflow_7d_sum"),
        pl.col("netflow_total").rolling_sum(30).alias("netflow_30d_sum"),
        pl.col("netflow_total").rolling_sum(90).alias("netflow_90d_sum"),
        pl.col("netflow_total").rolling_mean(7).alias("netflow_7d_avg"),
        pl.col("netflow_total").rolling_mean(30).alias("netflow_30d_avg"),
    ])
    # Z-score normalized netflow: negative = outflow = bullish
    df_n = df_n.with_columns([
        _zscore(pl.col("netflow_7d_sum"), 365).alias("netflow_zscore"),
    ])
    df_n = df_n.with_columns([
        _tanh_squash(-pl.col("netflow_zscore"), 1.5).alias("sig_netflow_raw"),
        pl.when(
            (pl.col("netflow_7d_sum") < 0) & (pl.col("netflow_30d_sum") < 0) & (pl.col("netflow_90d_sum") < 0)
        ).then(0.5).when(
            (pl.col("netflow_7d_sum") > 0) & (pl.col("netflow_30d_sum") > 0) & (pl.col("netflow_90d_sum") > 0)
        ).then(-0.5).otherwise(0.0).alias("netflow_align"),
    ])
    df_n = df_n.with_columns([
        (pl.col("sig_netflow_raw") + pl.col("netflow_align")).clip(-2.0, 2.0).alias("sig_netflow"),
    ])

    # ---- 3. Whale Ratio ----
    df_w = data["whale_ratio"].select(["start_time", "exchange_whale_ratio"])
    df_w = df_w.with_columns([
        pl.col("exchange_whale_ratio").rolling_mean(30).alias("whale_ratio_30d_ma"),
        _zscore(pl.col("exchange_whale_ratio"), 365).alias("whale_ratio_zscore"),
    ])
    # Lower whale ratio = less whale selling dominance = bullish
    df_w = df_w.with_columns([
        _tanh_squash(-pl.col("whale_ratio_zscore"), 1.5).alias("sig_whale"),
    ])

    # ---- 4. Stablecoin Reserve ----
    df_s = data["stable_reserve"].select(["start_time", "reserve"]).rename({"reserve": "stable_reserve"})
    df_s = df_s.with_columns([
        pl.col("stable_reserve").pct_change(7).alias("stable_7d_chg"),
        pl.col("stable_reserve").pct_change(30).alias("stable_30d_chg"),
        pl.col("stable_reserve").pct_change(90).alias("stable_90d_chg"),
        _zscore(pl.col("stable_reserve"), 365).alias("stable_zscore"),
    ])
    # Higher stablecoin reserve = more buying power parked = bullish
    df_s = df_s.with_columns([
        _tanh_squash(pl.col("stable_zscore"), 1.5).alias("sig_stable_raw"),
        pl.when(
            (pl.col("stable_7d_chg") > 0) & (pl.col("stable_30d_chg") > 0) & (pl.col("stable_90d_chg") > 0)
        ).then(0.5).when(
            (pl.col("stable_7d_chg") < 0) & (pl.col("stable_30d_chg") < 0) & (pl.col("stable_90d_chg") < 0)
        ).then(-0.5).otherwise(0.0).alias("stable_align"),
    ])
    df_s = df_s.with_columns([
        (pl.col("sig_stable_raw") + pl.col("stable_align")).clip(-2.0, 2.0).alias("sig_stable"),
    ])

    # ---- 5. Fund Flow Ratio ----
    df_f = data["fund_flow_ratio"].select(["start_time", "fund_flow_ratio"])
    df_f = df_f.with_columns([
        pl.col("fund_flow_ratio").rolling_mean(30).alias("ffr_30d_ma"),
        _zscore(pl.col("fund_flow_ratio"), 365).alias("ffr_zscore"),
    ])
    # Lower FFR = less exchange-bound flow = bullish
    df_f = df_f.with_columns([
        _tanh_squash(-pl.col("ffr_zscore"), 1.5).alias("sig_ffr"),
    ])

    # ---- 6. MPI ----
    df_m = data["mpi"].select(["start_time", "mpi"])
    df_m = df_m.with_columns([
        pl.col("mpi").rolling_mean(30).alias("mpi_30d_ma"),
    ])
    # MPI > 2 = miners over-selling. Scale: mpi of 2 -> z of +2 (scaled)
    df_m = df_m.with_columns([
        (-_tanh_squash((pl.col("mpi") - 1.0) / 1.0, 1.0)).alias("sig_mpi"),
    ])

    # ---- Join everything ----
    all_times = pl.concat([
        df_r.select("start_time"), df_n.select("start_time"), df_w.select("start_time"),
        df_s.select("start_time"), df_f.select("start_time"), df_m.select("start_time"),
    ]).unique().sort("start_time")

    joined = (all_times
        .join(df_r, on="start_time", how="left")
        .join(df_n, on="start_time", how="left")
        .join(df_w, on="start_time", how="left")
        .join(df_s, on="start_time", how="left")
        .join(df_f, on="start_time", how="left")
        .join(df_m, on="start_time", how="left")
    )

    # ---- Composite Score (weighted) ----
    # Weights: reserve=0.25, netflow=0.25, whale=0.15, stable=0.15, ffr=0.10, mpi=0.10
    w_reserve, w_netflow, w_whale, w_stable, w_ffr, w_mpi = 0.25, 0.25, 0.15, 0.15, 0.10, 0.10

    joined = joined.with_columns([
        (pl.col("sig_reserve").fill_null(0) * w_reserve
         + pl.col("sig_netflow").fill_null(0) * w_netflow
         + pl.col("sig_whale").fill_null(0) * w_whale
         + pl.col("sig_stable").fill_null(0) * w_stable
         + pl.col("sig_ffr").fill_null(0) * w_ffr
         + pl.col("sig_mpi").fill_null(0) * w_mpi)
        .alias("composite_whale_score"),
    ])

    # Rescale composite from [-2, 2] to roughly [-4, 4] for compatibility with dashboard
    joined = joined.with_columns([
        (pl.col("composite_whale_score") * 2.0).alias("composite_whale_score"),
    ])

    # Signal momentum (7d change of composite)
    joined = joined.with_columns([
        (pl.col("composite_whale_score") - pl.col("composite_whale_score").shift(7)).alias("whale_momentum"),
    ])

    return joined


def latest_summary(df: pl.DataFrame) -> dict:
    row = df.tail(1).to_dicts()[0]
    score = row["composite_whale_score"]
    momentum = row.get("whale_momentum", 0) or 0

    # Direction
    if score is None:
        score = 0
    if score >= 2.5:
        status = "STRONG_ACCUMULATION"
    elif score >= 1.0:
        status = "MODERATE_ACCUMULATION"
    elif score >= -1.0:
        status = "NEUTRAL"
    elif score >= -2.5:
        status = "MODERATE_DISTRIBUTION"
    else:
        status = "STRONG_DISTRIBUTION"

    # Momentum description
    if momentum > 0.3:
        trend = "IMPROVING (turning more bullish)"
    elif momentum < -0.3:
        trend = "DETERIORATING (turning more bearish)"
    else:
        trend = "STABLE"

    # Interpretation based on individual signals
    sigs = {
        "reserve": row.get("sig_reserve", 0) or 0,
        "netflow": row.get("sig_netflow", 0) or 0,
        "whale": row.get("sig_whale", 0) or 0,
        "stable": row.get("sig_stable", 0) or 0,
        "ffr": row.get("sig_ffr", 0) or 0,
        "mpi": row.get("sig_mpi", 0) or 0,
    }
    bullish_count = sum(1 for v in sigs.values() if v > 0.3)
    bearish_count = sum(1 for v in sigs.values() if v < -0.3)

    if bullish_count >= 4:
        detail = "多項指標顯示強力吸籌"
    elif bearish_count >= 4:
        detail = "多項指標顯示大量派發"
    elif bullish_count > bearish_count:
        detail = f"偏向累積 ({bullish_count}/{len(sigs)} 指標偏多)"
    elif bearish_count > bullish_count:
        detail = f"偏向派發 ({bearish_count}/{len(sigs)} 指標偏空)"
    else:
        detail = "多空指標均衡"

    return {
        "date": str(row["start_time"]),
        "status": status,
        "score": round(score, 2),
        "momentum": round(momentum, 2),
        "trend": trend,
        "detail": detail,
        "metrics": {
            "reserve_btc": row.get("reserve"),
            "reserve_7d_chg": row.get("reserve_7d_chg"),
            "reserve_30d_chg": row.get("reserve_30d_chg"),
            "reserve_zscore": row.get("reserve_zscore"),
            "sig_reserve": round(sigs["reserve"], 3),
            "netflow_7d_sum": row.get("netflow_7d_sum"),
            "netflow_30d_sum": row.get("netflow_30d_sum"),
            "sig_netflow": round(sigs["netflow"], 3),
            "whale_ratio": row.get("exchange_whale_ratio"),
            "whale_ratio_zscore": row.get("whale_ratio_zscore"),
            "sig_whale": round(sigs["whale"], 3),
            "stable_reserve_usd": row.get("stable_reserve"),
            "stable_zscore": row.get("stable_zscore"),
            "sig_stable": round(sigs["stable"], 3),
            "fund_flow_ratio": row.get("fund_flow_ratio"),
            "sig_ffr": round(sigs["ffr"], 3),
            "mpi": row.get("mpi"),
            "sig_mpi": round(sigs["mpi"], 3),
        }
    }
