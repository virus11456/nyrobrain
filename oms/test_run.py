import json
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("oms_run", Path(__file__).with_name("run.py"))
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)


class _Alpha:
    def __init__(self, id):
        self.id = id


def test_namespace_prefixes_user_id():
    assert run.namespace("u1", "bqp_ml021") == "u1_bqp_ml021"


def test_prime_create_empty_payload():
    p = run.prime_create_empty_payload("u1_bqp_x", "100000.00")
    assert p == {
        "portfolioName": "u1_bqp_x",
        "tier": "nyrobrain_paper",
        "initialAmount": "100000.00",
        "portfolioId": "u1_bqp_x",
        "omsId": "u1_bqp_x",
    }
    assert p["tier"] == run.PRIME_PAPER_TIER


def test_build_alpha_id_map_uses_original_ids_as_keys():
    alphas = [_Alpha("alpha_001"), _Alpha("alpha_002")]
    assert run.build_alpha_id_map("u1", alphas) == {
        "alpha_001": "u1_alpha_001",
        "alpha_002": "u1_alpha_002",
    }


def test_read_prime_api_key_reads_extra_key(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"oms_id": "x", "prime_api_key": "pk_123"}))
    assert run.read_prime_api_key(str(p)) == "pk_123"


def test_read_prime_api_key_missing_raises(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"oms_id": "x"}))
    with pytest.raises(ValueError):
        run.read_prime_api_key(str(p))


def test_nats_grpc_addr_default(monkeypatch):
    monkeypatch.delenv("BQ_AEGIS_NATS_GRPC_ADDR", raising=False)
    assert run.nats_grpc_addr("BQ_AEGIS_NATS_GRPC_ADDR", run.DEFAULT_AEGIS) == run.DEFAULT_AEGIS


def test_nats_grpc_addr_override(monkeypatch):
    monkeypatch.setenv("BQ_AEGIS_NATS_GRPC_ADDR", "host:50052")
    assert run.nats_grpc_addr("BQ_AEGIS_NATS_GRPC_ADDR", run.DEFAULT_AEGIS) == "host:50052"


def test_require_env_present(monkeypatch):
    monkeypatch.setenv("FOO_X", "v")
    assert run.require_env("FOO_X") == "v"


def test_require_env_missing_raises(monkeypatch):
    monkeypatch.delenv("FOO_X", raising=False)
    with pytest.raises(RuntimeError):
        run.require_env("FOO_X")


def test_read_prime_api_key_empty_raises(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"prime_api_key": ""}))
    with pytest.raises(ValueError):
        run.read_prime_api_key(str(p))


def test_load_setup_portfolio_from_py_path(tmp_path):
    mod = tmp_path / "p_mod.py"
    mod.write_text("async def setup_portfolio():\n    return 1, 2, 3, 4\n")
    fn = run.load_setup_portfolio(str(mod))
    assert callable(fn) and fn.__name__ == "setup_portfolio"
