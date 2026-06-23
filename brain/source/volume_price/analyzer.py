import polars as pl
import numpy as np


def load_ohlcv(data_dir: str) -> pl.DataFrame:
    path = f"{data_dir}/btc_spot.parquet"
    return pl.read_parquet(path).sort("start_time").unique(subset=["start_time"])


def _zscore(col: pl.Expr, window: int = 365) -> pl.Expr:
    return (col - col.rolling_mean(window, min_periods=60)) / col.rolling_std(window, min_periods=60)


def _tanh_squash(x: pl.Expr, scale: float = 1.5) -> pl.Expr:
    return (x / scale).tanh() * 2.0


def _rolling_corr(a: pl.Expr, b: pl.Expr, window: int) -> pl.Expr:
    ma = a.rolling_mean(window, min_periods=window // 2)
    mb = b.rolling_mean(window, min_periods=window // 2)
    da = a - ma
    db = b - mb
    num = (da * db).rolling_sum(window, min_periods=window // 2)
    den_a = (da * da).rolling_sum(window, min_periods=window // 2).sqrt()
    den_b = (db * db).rolling_sum(window, min_periods=window // 2).sqrt()
    return num / (den_a * den_b)


def compute_signals(df: pl.DataFrame):
    df = df.with_columns([
        pl.col("volume").rolling_mean(5).alias("vol_5d_ma"),
        pl.col("volume").rolling_mean(20).alias("vol_20d_ma"),
        pl.col("volume").rolling_mean(50).alias("vol_50d_ma"),
        pl.col("close").rolling_mean(5).alias("close_5d_ma"),
        pl.col("close").rolling_mean(20).alias("close_20d_ma"),
        pl.col("close").rolling_mean(50).alias("close_50d_ma"),
    ])

    # ---- OBV ----
    df = df.with_columns([
        pl.when(pl.col("close") > pl.col("close").shift(1))
        .then(pl.col("volume"))
        .when(pl.col("close") < pl.col("close").shift(1))
        .then(-pl.col("volume"))
        .otherwise(0)
        .alias("obv_delta")
    ])
    df = df.with_columns([pl.col("obv_delta").cum_sum().alias("obv")])

    # ---- Volume Z-Score ----
    df = df.with_columns([
        _zscore(pl.col("volume"), 90).alias("vol_zscore_90d"),
    ])

    # ---- Signal 1: Volume Expansion/Contraction ----
    # Expanding volume = healthy trend confirmation (in either direction)
    # Contracting volume = weakening momentum / potential reversal
    df = df.with_columns([
        pl.col("vol_5d_ma").pct_change(5).alias("vol_5d_momentum"),
    ])
    df = df.with_columns([
        _tanh_squash(pl.col("vol_5d_momentum") * 10, 1.5).alias("sig_vol_momentum"),
    ])

    # ---- Signal 2: Price-Volume Direction Alignment ----
    # Healthy: price up + volume up, or price down + volume down (drying up = selling exhaustion)
    # Divergent: price up + volume down (bearish), price down + volume up (bullish potential)
    df = df.with_columns([
        pl.col("close").pct_change(7).alias("px_7d_chg"),
        pl.col("close").pct_change(30).alias("px_30d_chg"),
        pl.col("volume").pct_change(7).alias("vol_7d_chg"),
        pl.col("volume").pct_change(30).alias("vol_30d_chg"),
    ])

    # Signal: bullish when (price up & vol up) or (price down & vol UP) -> vol UP on down move = accumulation
    df = df.with_columns([
        pl.when(
            (pl.col("px_7d_chg") < -0.02) & (pl.col("vol_7d_chg") > 0.05)
        ).then(1.5)  # price down, volume up -> potential bottom (smart money accumulating)
        .when(
            (pl.col("px_7d_chg") > 0.02) & (pl.col("vol_7d_chg") > 0.05)
        ).then(1.0)  # price up, volume up -> healthy uptrend
        .when(
            (pl.col("px_7d_chg") > 0.02) & (pl.col("vol_7d_chg") < -0.10)
        ).then(-1.5)  # price up, volume down significantly -> bearish divergence
        .when(
            (pl.col("px_7d_chg") < -0.02) & (pl.col("vol_7d_chg") < -0.10)
        ).then(0.5)  # price down, volume down -> selling exhaustion
        .otherwise(0.0)
        .alias("sig_px_vol_align"),
    ])

    # ---- Signal 3: OBV-Price Rolling Correlation (30d) ----
    df = df.with_columns([
        _rolling_corr(pl.col("close"), pl.col("obv"), 30).alias("obv_price_corr_30d"),
    ])
    # Negative correlation = divergence = bullish potential (OBV holding up while price falling)
    # Positive correlation = OBV confirming price
    df = df.with_columns([
        pl.when(pl.col("obv_price_corr_30d") < -0.5).then(1.5)
        .when(pl.col("obv_price_corr_30d") < -0.2).then(0.8)
        .when(pl.col("obv_price_corr_30d") > 0.8).then(-0.5)
        .otherwise(0.0)
        .alias("sig_obv_corr"),
    ])

    # ---- Signal 4: Volume Z-Score Extreme ----
    # Very high volume = climax (could be either direction, ambiguous)
    # Very low volume = disinterest / consolidation
    df = df.with_columns([
        pl.when(pl.col("vol_zscore_90d") < -1.5).then(0.5)  # extremely low volume -> bottom zone
        .when(pl.col("vol_zscore_90d") > 2.5).then(-1.0)  # extremely high volume -> possible distribution top
        .otherwise(0.0)
        .alias("sig_vol_extreme"),
    ])

    # ---- Signal 5: Multi-timeframe volume trend ----
    df = df.with_columns([
        pl.when(
            (pl.col("vol_5d_ma") < pl.col("vol_20d_ma")) &
            (pl.col("vol_20d_ma") < pl.col("vol_50d_ma"))
        ).then(0.5)  # consistent volume decline -> selling exhaustion potential
        .when(
            (pl.col("vol_5d_ma") > pl.col("vol_20d_ma")) &
            (pl.col("vol_20d_ma") > pl.col("vol_50d_ma"))
        ).then(-0.5)  # consistent volume expansion -> possible climax
        .otherwise(0.0)
        .alias("sig_vol_mtf"),
    ])

    # ---- Composite VP Signal ----
    df = df.with_columns([
        (pl.col("sig_px_vol_align").fill_null(0) * 0.35
         + pl.col("sig_obv_corr").fill_null(0) * 0.25
         + pl.col("sig_vol_momentum").fill_null(0) * 0.15
         + pl.col("sig_vol_extreme").fill_null(0) * 0.10
         + pl.col("sig_vol_mtf").fill_null(0) * 0.15)
        .alias("vp_signal"),
    ])

    # Signal momentum
    df = df.with_columns([
        (pl.col("vp_signal") - pl.col("vp_signal").shift(7)).alias("vp_momentum"),
    ])

    return df


def latest_summary(df: pl.DataFrame) -> dict:
    row = df.tail(1).to_dicts()[0]
    signal = row.get("vp_signal", 0) or 0
    momentum = row.get("vp_momentum", 0) or 0

    if signal >= 1.5:
        status = "BULLISH_DIVERGENCE"
    elif signal >= 0.5:
        status = "MILD_BULLISH"
    elif signal >= -0.5:
        status = "NEUTRAL"
    elif signal >= -1.5:
        status = "MILD_BEARISH"
    else:
        status = "BEARISH_DIVERGENCE"

    if momentum > 0.2:
        trend = "IMPROVING"
    elif momentum < -0.2:
        trend = "DETERIORATING"
    else:
        trend = "STABLE"

    # Volume trend analysis
    vol_5d = row.get("vol_5d_ma", 0) or 0
    vol_20d = row.get("vol_20d_ma", 0) or 0
    close_5d = row.get("close_5d_ma", 0) or 0
    close_20d = row.get("close_20d_ma", 0) or 0
    obv_corr = row.get("obv_price_corr_30d", 0) or 0
    vol_z = row.get("vol_zscore_90d", 0) or 0

    if vol_5d < vol_20d and close_5d < close_20d:
        vol_price_desc = "价跌量缩 — 卖压衰竭，潜在底部"
    elif vol_5d < vol_20d and close_5d > close_20d:
        vol_price_desc = "价涨量缩 — 买盘不足，警惕回调"
    elif vol_5d > vol_20d and close_5d > close_20d:
        vol_price_desc = "价涨量增 — 上升趋势健康"
    elif vol_5d > vol_20d and close_5d < close_20d:
        vol_price_desc = "价跌量增 — 有承接盘，关注反转"
    else:
        vol_price_desc = "量价同步"

    if obv_corr < -0.3:
        obv_desc = f"OBV-price correlation {obv_corr:.2f}: OBV holding up while price declining -> bullish divergence"
    elif obv_corr > 0.7:
        obv_desc = f"OBV-price correlation {obv_corr:.2f}: OBV confirming price direction"
    else:
        obv_desc = f"OBV-price correlation {obv_corr:.2f}: no strong divergence"

    return {
        "date": str(row["start_time"]),
        "status": status,
        "signal_score": round(signal, 2),
        "momentum": round(momentum, 2),
        "trend": trend,
        "vol_price_desc": vol_price_desc,
        "obv_desc": obv_desc,
        "metrics": {
            "close": row.get("close"),
            "volume": row.get("volume"),
            "vol_zscore_90d": vol_z,
            "vol_5d_ma": vol_5d,
            "vol_20d_ma": vol_20d,
            "close_5d_ma": close_5d,
            "close_20d_ma": close_20d,
            "obv": row.get("obv"),
            "obv_price_corr_30d": obv_corr,
            "px_7d_chg": row.get("px_7d_chg"),
            "vol_7d_chg": row.get("vol_7d_chg"),
        }
    }
