"""Тесты bschekbot-клиента (core/bscheck.py) — проба нод через операторов РФ."""
import json

import httpx
import pytest
from unittest.mock import patch

from web.backend.core import bscheck as bs


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patched_client(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw)
    return factory


def _token():
    return patch.object(bs, "_stored_token", return_value="bsk_live_TEST")


# ── summarize ────────────────────────────────────────────────────


class TestSummarize:
    def test_counts_passed_and_sorts_ops(self):
        result = {"cost_credits": 12, "by_target": {"1.2.3.4": {"by_operator": {
            "ufo1:mts": {"ok": True, "channel_state": "DPI_ON", "latency_ms": 140},
            "dfo1:tele2": {"ok": False, "channel_state": "DPI_ON", "error": "timeout"}}}},
            "skipped_dpi_off": [{"operator": "beeline"}]}
        s = bs.summarize(result, "1.2.3.4")
        assert s["passed"] == 1 and s["total"] == 2
        assert s["cost_credits"] == 12 and s["skipped_dpi_off"] == ["beeline"]
        assert s["operators"][0]["op"] == "dfo1:tele2"  # отсортировано по op

    def test_empty(self):
        s = bs.summarize({}, "x")
        assert s["passed"] == 0 and s["total"] == 0 and s["operators"] == []


# ── Клиент ───────────────────────────────────────────────────────


class TestClient:
    @pytest.mark.asyncio
    async def test_verify_and_account(self):
        def h(r):
            assert r.headers.get("Authorization") == "Bearer bsk_live_TEST"
            if r.url.path == "/v1/account":
                return httpx.Response(200, json={"balance_credits": 4500, "tier": "silver"})
            return httpx.Response(404)

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await bs.verify_token("bsk_live_TEST") is True
        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            acc = await bs.get_account()
        assert acc["balance_credits"] == 4500

    @pytest.mark.asyncio
    async def test_operators(self):
        def h(r):
            return httpx.Response(200, json={"is_multiworker": True, "operators": [
                {"id": "mts", "name": "МТС", "op_key": "ufo1:mts",
                 "channel_state": "DPI_ON", "alive": True}]})

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            ops = await bs.get_operators()
        assert ops[0]["op_key"] == "ufo1:mts" and ops[0]["channel_state"] == "DPI_ON"

    @pytest.mark.asyncio
    async def test_probe_sends_idempotency_and_body(self):
        seen = {}

        def h(r):
            if r.url.path == "/v1/probe":
                seen["idem"] = r.headers.get("Idempotency-Key")
                seen["body"] = json.loads(r.content.decode())
                return httpx.Response(200, json={"outcome": "done", "cost_credits": 12, "by_target": {
                    "1.2.3.4": {"by_operator": {"ufo1:mts": {"ok": True, "channel_state": "DPI_ON"}}}}})
            return httpx.Response(404)

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            res = await bs.probe({"target": "1.2.3.4", "operators": ["ufo1:mts"],
                                  "probes": {"tcp": True}, "dpi": "on"})
        assert seen["idem"]  # Idempotency-Key проставлен на платном POST
        assert seen["body"]["target"] == "1.2.3.4"
        assert res["cost_credits"] == 12

    @pytest.mark.asyncio
    async def test_error_envelope(self):
        def h(r):
            return httpx.Response(402, json={"error": {
                "code": "insufficient_credits", "message": "не хватает баланса"}})

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            with pytest.raises(bs.BscheckError, match="баланса"):
                await bs.probe({"target": "1.2.3.4"})

    @pytest.mark.asyncio
    async def test_not_configured(self):
        with patch.object(bs, "_stored_token", return_value=None):
            with pytest.raises(bs.BscheckError, match="не настроен"):
                await bs.get_operators()

    @pytest.mark.asyncio
    async def test_verify_false_on_unauthenticated(self):
        def h(r):
            return httpx.Response(401, json={"error": {"code": "unauthenticated"}})

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await bs.verify_token("bad") is False


# ── summarize_all (мульти-цель) ──────────────────────────────────


class TestSummarizeAll:
    def test_multi_target(self):
        result = {"by_target": {
            "1.1.1.1": {"by_operator": {"ufo1:mts": {"ok": True, "channel_state": "DPI_ON"}}},
            "2.2.2.2": {"by_operator": {"ufo1:mts": {"ok": False, "channel_state": "DPI_ON"}}}}}
        rows = bs.summarize_all(result)
        assert len(rows) == 2
        assert rows[0]["target"] == "1.1.1.1" and rows[0]["passed"] == 1
        assert rows[1]["target"] == "2.2.2.2" and rows[1]["passed"] == 0


# ── Скан /24 и VLESS ─────────────────────────────────────────────


class TestScansVless:
    @pytest.mark.asyncio
    async def test_scan_submit_and_status(self):
        def h(r):
            if r.url.path == "/v1/scans" and r.method == "POST":
                assert r.headers.get("Idempotency-Key")
                return httpx.Response(200, json={"outcome": "queued", "scan_id": 12345, "state": "running"})
            if r.url.path == "/v1/scans/12345":
                return httpx.Response(200, json={"scan_id": 12345, "state": "done",
                                                 "result": {"up_n": 7, "total": 256}})
            return httpx.Response(404)

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            sub = await bs.scans_submit({"cidr": "1.2.3.0/24", "operators": ["ufo1:mts"]})
            st = await bs.scans_status("12345")
        assert sub["scan_id"] == 12345 and st["state"] == "done" and st["result"]["up_n"] == 7

    @pytest.mark.asyncio
    async def test_scan_preview(self):
        def h(r):
            return httpx.Response(200, json={"cost_credits": 240, "total_ips": 256})

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            p = await bs.scans_preview({"cidr": "1.2.3.0/24"})
        assert p["cost_credits"] == 240

    @pytest.mark.asyncio
    async def test_vless_submit_and_status(self):
        def h(r):
            if r.url.path == "/v1/vless" and r.method == "POST":
                assert r.headers.get("Idempotency-Key")
                return httpx.Response(200, json={"outcome": "queued", "test_id": 88, "cost_credits": 30})
            if r.url.path == "/v1/vless/88":
                return httpx.Response(200, json={"test_id": 88, "state": "done", "result_ready": True,
                    "result": [{"server_name": "s1", "ok": True, "tunnel_up": True, "speed_mbps": 42.0}]})
            return httpx.Response(404)

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            sub = await bs.vless_submit({"raw_input": "vless://x", "dpi": "on"})
            st = await bs.vless_status("88")
        assert sub["test_id"] == 88 and st["result_ready"] is True
        assert st["result"][0]["speed_mbps"] == 42.0
