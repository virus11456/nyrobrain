"""Nyrobrain OMS paper-trade entrypoint.

Runs an existing brain/portfolio/<...> portfolio live against the configured
exchange (bybit demo) via the adrs OMS, as a long-running job.

    uv run python oms/run.py <portfolio.py path or module> -f <config.json> [-c <cache_dir>]

Heavy imports (adrs, NATS) live inside main() so this module imports cleanly
for unit tests.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import os
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_AEGIS = "aegis-nats.balaenaquant.com"
DEFAULT_FLOW = "flow-nats.balaenaquant.com"
DEFAULT_PRIME_API = "https://prime.balaenaquant.com"

# Tier is fixed for Nyrobrain paper-trade runs.
PRIME_PAPER_TIER = "nyrobrain_paper"

# Dashboard-metric JetStream namespace on the aegis NATS. MetricBuilder (in the
# OMS and the executors) prefixes every metric insert with this; the adrs
# default "public_ts" has no responder on the aegis NATS.
AEGIS_METRIC_NAMESPACE = "aegis_ts"


def namespace(uid: str, ident: str) -> str:
    """Prefix an id with the user id so two users' portfolios/alphas don't
    collide on the shared NATS subjects."""
    return f"{uid}_{ident}"


def build_alpha_id_map(uid: str, alphas: list[Any]) -> dict[str, str]:
    """Map each alpha's ORIGINAL id to its user-namespaced id. Passed to
    run_portfolio (which applies it); built from original ids because
    signal_df/metadata_df/weight_df are keyed by them."""
    return {a.id: namespace(uid, a.id) for a in alphas}


def read_prime_api_key(config_path: str) -> str:
    """`prime_api_key` lives in config.json next to the OMS Config fields (the
    pydantic Config ignores it). Read it raw."""
    data = json.loads(Path(config_path).read_text())
    key = data.get("prime_api_key")
    if not key:
        raise ValueError(f"'prime_api_key' missing/empty in {config_path}")
    return key


def prime_create_empty_payload(
    portfolio_id: str, initial_amount: str
) -> dict[str, str]:
    """Multipart form fields for Prime's portfolio-create-empty endpoint.
    `portfolio_id` is the namespaced id (so it matches the subjects the OMS
    publishes / the Prime dashboard keys by); portfolioName mirrors it; tier is
    always the Nyrobrain paper tier; initialAmount comes from the user's config."""
    return {
        "portfolioName": portfolio_id,
        "tier": PRIME_PAPER_TIER,
        "initialAmount": initial_amount,
        "portfolioId": portfolio_id,
        "omsId": portfolio_id,
    }


def prime_create_alphas_payload(
    alphas: list[Any],
    alpha_id_map: dict[str, str],
    base_asset_by_id: dict[str, str],
    portfolio_id: str,
) -> dict[str, Any]:
    """JSON body for Prime's alpha-create endpoint. One entry per alpha, using
    the namespaced alphaId/portfolioId (matches the subjects the OMS publishes /
    the dashboard keys by). `alphas` still carry their ORIGINAL ids here (the
    alpha_id_map rename happens inside run_portfolio), so map id->namespaced and
    look up base_asset by the original id. The original id doubles as the display
    name (Alpha has no separate name)."""
    return {
        "alphas": [
            {
                "alphaId": alpha_id_map.get(a.id, a.id),
                "name": a.id,
                "baseAsset": base_asset_by_id.get(a.id, ""),
                "portfolioId": portfolio_id,
                "isActive": True,
            }
            for a in alphas
        ]
    }


def require_env(name: str) -> str:
    """Return a required env var or raise a clear startup error (a bare
    KeyError in a job log is hard to diagnose)."""
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"{name} environment variable is required but missing/empty")
    return val


def nats_grpc_addr(env_var: str, default: str) -> str:
    return os.environ.get(env_var, default)


def load_setup_portfolio(module_arg: str) -> Callable[..., Awaitable[Any]]:
    """Import `setup_portfolio` from a dotted module or a .py file path."""
    if module_arg.endswith(".py") or "/" in module_arg or os.sep in module_arg:
        path = Path(module_arg)
        if path.suffix != ".py":
            path = path.with_suffix(".py")
        path = path.resolve()
        sys.path.insert(0, str(path.parent))
        module_name = path.stem
    else:
        module_name = module_arg
    return importlib.import_module(module_name).setup_portfolio


async def main() -> None:
    parser = argparse.ArgumentParser(prog="oms-run")
    parser.add_argument(
        "module", help="portfolio.py path or module exposing setup_portfolio"
    )
    parser.add_argument("-f", "--file", required=True, help="Path to config.json")
    parser.add_argument(
        "-c",
        "--cache-dir",
        default=os.environ.get("NYROBRAIN_DATA_DIR", "outdir"),
        help="DataLoader cache dir (default: $NYROBRAIN_DATA_DIR or outdir)",
    )
    parser.add_argument(
        "-l",
        "--log-file",
        default="oms/logs/portfolio_oms.log",
        help="Log file path (kept under a dir so it doesn't litter /workspace).",
    )
    args = parser.parse_args()

    import logging

    import httpx
    from adrs.data import DataLoader, DatasourceStream
    from adrs.execution import run_portfolio
    from adrs.io.stream import PublicMetricStream, PublicNatsDatasourceStream
    from adrs.logging import (
        make_colorlog_stream_handler,
        make_logging_timed_rotating_file_handler,
        setup_logger,
    )
    from adrs.oms.config import FileConfigManager
    from adrs.oms.oms import OMS
    from adrs.oms.rate_limit.rate_limiter import BybitRateLimiter
    from aion import Scheduler
    from nats_client import NATSClient

    # The rotating file handler does not create parent dirs — make them so the
    # log lands under its directory (e.g. oms/logs/) instead of failing.
    Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)
    setup_logger(
        log_level=logging.INFO,
        handlers=[
            make_colorlog_stream_handler(),
            make_logging_timed_rotating_file_handler(
                filename=args.log_file, backupCount=0
            ),
        ],
    )

    uid = require_env("USER_ID")
    prime = read_prime_api_key(args.file)

    setup_portfolio = load_setup_portfolio(args.module)
    # Live runs need signal_df to reach ~now (PortfolioExecutor rejects a stale
    # last row). run.py can't reach make_datamap/generate_signal_df directly, so
    # it passes hints THROUGH setup_portfolio (see docs/pipelines/2-portfolio.md):
    #   end_time=now  → fetch/build signals up to the current time
    #   live=True     → setup_portfolio sets generate_signal_df(forward_fill_to_end=True),
    #                   carrying the last signal forward so a mixed-cadence
    #                   (e.g. 1h+24h) signal_df still reaches ~now.
    # Both are signature-gated for backward compat: portfolios that don't accept
    # them still run (but may be stale — we warn).
    sig_params = inspect.signature(setup_portfolio).parameters
    kwargs: dict[str, Any] = {}
    if "end_time" in sig_params:
        kwargs["end_time"] = datetime.now(timezone.utc)
    if "live" in sig_params:
        kwargs["live"] = True
    if "end_time" not in sig_params:
        logging.warning(
            "[oms] setup_portfolio() has no 'end_time'/'live' params — signal_df "
            "may be stale for a live run (PortfolioExecutor rejects stale rows). "
            "Update it per docs/pipelines/2-portfolio.md."
        )
    result = await setup_portfolio(**kwargs)
    try:
        portfolio, alphas, _evaluator, _datamap = result
    except (TypeError, ValueError) as e:
        raise RuntimeError(
            "setup_portfolio() must return (portfolio, alphas, evaluator, datamap); "
            f"see docs/pipelines/2-portfolio.md (got: {result!r})"
        ) from e

    metric_nats = NATSClient(
        grpc_addr=nats_grpc_addr("BQ_AEGIS_NATS_GRPC_ADDR", DEFAULT_AEGIS),
        api_key=prime,
        tls=True,
    )
    ms = PublicMetricStream(nats=metric_nats)
    await ms.init()

    flow_nats = NATSClient(
        grpc_addr=nats_grpc_addr("BQ_FLOW_NATS_GRPC_ADDR", DEFAULT_FLOW),
        api_key=prime,
        tls=True,
    )
    ds: DatasourceStream = PublicNatsDatasourceStream(flow_nats=flow_nats)

    dataloader = DataLoader(
        data_dir=args.cache_dir,
        credentials={"cybotrade_api_key": uid},
        cybotrade_api_url=require_env("DATASOURCE_PROXY_URL"),
    )

    scheduler = Scheduler()

    # The OMS reloads config.json from disk every ~2s (on_refresh_config →
    # config.refresh() → load()), so prefixing the ids in memory once would be
    # wiped on the next reload — reverting portfolio_id to the un-prefixed file
    # value while run_portfolio keeps publishing under the prefixed id. Override
    # load() so the USER_ID prefix is re-applied on EVERY reload; the file stays
    # the user's original ids. (oms_id == portfolio_id is preserved.)
    class _PrefixedConfigManager(FileConfigManager):
        def __init__(self, path: str, prefix_uid: str):
            super().__init__(path)
            self._prefix_uid = prefix_uid

        async def load(self):
            cfg = await super().load()
            cfg.oms_id = namespace(self._prefix_uid, cfg.oms_id)
            cfg.portfolio_id = namespace(self._prefix_uid, cfg.portfolio_id)
            return cfg

    config = _PrefixedConfigManager(args.file, uid)
    await config.setup()

    portfolio.id = config.config.portfolio_id  # namespaced via load() override
    alpha_id_map = build_alpha_id_map(uid, alphas)

    # Ensure the portfolio exists in Prime before the OMS starts publishing to
    # it, so the run shows up on the Prime dashboard. Created with the
    # namespaced id (matches what the OMS/run_portfolio publish under). Best
    # effort: a non-2xx (e.g. already created on an autostart restart) is logged
    # but does not block the run.
    prime_api = os.environ.get("PRIME_API_URL", DEFAULT_PRIME_API).rstrip("/")
    payload = prime_create_empty_payload(
        portfolio_id=config.config.portfolio_id,
        initial_amount=str(config.config.initial_balance),
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{prime_api}/api/portfolio-create-empty",
                headers={"x-api-key": prime},
                files={k: (None, v) for k, v in payload.items()},
            )
        if resp.is_success:
            logging.info("[prime] portfolio %s ready", config.config.portfolio_id)
        else:
            logging.warning(
                "[prime] portfolio-create-empty returned %s: %s (continuing)",
                resp.status_code,
                resp.text[:500],
            )
    except Exception as err:  # network error — don't block paper trading
        logging.warning("[prime] portfolio-create-empty failed: %s (continuing)", err)

    # Register the portfolio's alphas in Prime so they show on the dashboard,
    # keyed by the same namespaced ids the OMS publishes under. base_asset comes
    # from the portfolio's metadata_df (still original-id-keyed at this point).
    # Best effort, same as the portfolio create above.
    base_asset_by_id = dict(
        zip(
            portfolio.metadata_df["custom_id"].to_list(),
            portfolio.metadata_df["base_asset"].to_list(),
        )
    )
    alphas_payload = prime_create_alphas_payload(
        alphas=alphas,
        alpha_id_map=alpha_id_map,
        base_asset_by_id=base_asset_by_id,
        portfolio_id=config.config.portfolio_id,
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{prime_api}/api/alpha-create",
                headers={"x-api-key": prime, "Content-Type": "application/json"},
                json=alphas_payload,
            )
        if resp.is_success:
            logging.info(
                "[prime] %d alpha(s) registered", len(alphas_payload["alphas"])
            )
        else:
            logging.warning(
                "[prime] alpha-create returned %s: %s (continuing)",
                resp.status_code,
                resp.text[:500],
            )
    except Exception as err:  # network error — don't block paper trading
        logging.warning("[prime] alpha-create failed: %s (continuing)", err)

    # adrs OMS.run() wraps startup in `try: ... finally: _handle_shutdown()`,
    # and _handle_shutdown does `exit(0)` — which SILENTLY masks any startup
    # exception (you only see "Shutdown signal received", no traceback). Log the
    # real error in init() before it gets swallowed.
    class _LoggingOMS(OMS):
        async def init(self):
            try:
                await super().init()
            except BaseException:
                logging.exception("[oms] init() failed")
                raise

    # The dashboard-metric namespace moved from PublicMetricStream onto
    # MetricBuilder (adrs >= 1.3.0), so the OMS + executors each take an
    # insert_prefix. Signature-gated: on older adrs the stream still carried it,
    # but those workspaces are upgraded by the /paper-trade skill before running.
    rate_limiter = BybitRateLimiter(config=config)
    await rate_limiter.init()
    oms_params = inspect.signature(_LoggingOMS.__init__).parameters
    oms_kwargs: dict[str, Any] = {}
    if "insert_prefix" in oms_params:
        oms_kwargs["insert_prefix"] = AEGIS_METRIC_NAMESPACE
    # Subscribe to portfolio_signal under this user's namespace — must match the
    # PortfolioExecutor's signal_namespace (set via run_portfolio below).
    if "signal_namespace" in oms_params:
        oms_kwargs["signal_namespace"] = uid
    oms = _LoggingOMS(
        config=config, metric_stream=ms, rate_limiter=rate_limiter, **oms_kwargs
    )

    # Isolate this user's alpha signals on the shared NATS, and route dashboard
    # metrics into the aegis namespace. Both signature-gated for backward compat.
    run_portfolio_kwargs: dict[str, Any] = {}
    rp_params = inspect.signature(run_portfolio).parameters
    if "signal_namespace" in rp_params:
        run_portfolio_kwargs["signal_namespace"] = uid
    else:
        logging.warning(
            "[oms] adrs run_portfolio() has no 'signal_namespace' — alpha signals "
            "are NOT tenant-isolated on the shared NATS (upgrade to adrs >= 1.3.0)."
        )
    if "insert_prefix" in rp_params:
        run_portfolio_kwargs["insert_prefix"] = AEGIS_METRIC_NAMESPACE

    try:
        await asyncio.gather(
            scheduler.start(),
            run_portfolio(
                portfolio,
                alphas,
                dataloader=dataloader,
                metric_stream=ms,
                datasource_stream=ds,
                alpha_id_map=alpha_id_map,
                # Scope alpha-signal pub/sub to this user so the shared NATS
                # server doesn't deliver (or leak) other tenants' signals into
                # this portfolio. signature-gated: adrs < 1.2.10 lacks the param
                # (the run still works, just without isolation — we warn).
                **run_portfolio_kwargs,
            ),
            oms.run(),
        )
    except SystemExit:
        raise  # OMS _handle_shutdown calls exit(0); nothing to log
    except BaseException:
        # run_portfolio / scheduler failures (e.g. "signal_df is stale") would
        # otherwise be masked by the OMS finally's exit(0).
        logging.exception("[oms] run aborted")
        raise


if __name__ == "__main__":
    asyncio.run(main())
