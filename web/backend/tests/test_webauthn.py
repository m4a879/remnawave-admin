"""Тесты WebAuthn-сервиса: challenge-token, rp/origin, генерация опций."""
import json
from types import SimpleNamespace

import pytest
from webauthn.helpers import base64url_to_bytes

from web.backend.core import webauthn_svc as wa


def _req(host="admin.example.com", proto="https"):
    return SimpleNamespace(headers={"host": host, "x-forwarded-proto": proto},
                           url=SimpleNamespace(scheme=proto))


class TestChallengeToken:
    def test_roundtrip(self):
        tok = wa._make_token("wa_reg", b"\x01\x02\x03challenge-bytes-01", {"aid": 7})
        p = wa._read_token(tok, "wa_reg")
        assert p["aid"] == 7
        assert base64url_to_bytes(p["chal"]) == b"\x01\x02\x03challenge-bytes-01"

    def test_wrong_purpose(self):
        tok = wa._make_token("wa_reg", b"abcdefghij0123456789", {})
        with pytest.raises(wa.WebAuthnError):
            wa._read_token(tok, "wa_auth")


class TestRpOrigin:
    def test_forwarded_host_port(self):
        rp, origin = wa._rp_origin(_req("panel.foo.com:443", "https"))
        assert rp == "panel.foo.com" and origin == "https://panel.foo.com:443"


class TestBeginRegistration:
    @pytest.mark.asyncio
    async def test_produces_options(self):
        out = await wa.begin_registration(_req(), {"id": 5, "username": "admin"})
        assert "options" in out and "token" in out
        opts = json.loads(out["options"])
        assert opts["rp"]["id"] == "admin.example.com"
        assert opts["user"]["name"] == "admin"
        assert wa._read_token(out["token"], "wa_reg")["aid"] == 5
