"""Тесты OAuth-сервиса: state-token, redirect_uri, список провайдеров."""
from types import SimpleNamespace

import pytest

from web.backend.core import oauth_svc as oa


def _req(host="panel.example.com", proto="https"):
    return SimpleNamespace(headers={"host": host, "x-forwarded-proto": proto},
                           url=SimpleNamespace(scheme=proto))


class TestState:
    def test_roundtrip(self):
        p = oa._read_state(oa._make_state("google", "link", 9))
        assert p["provider"] == "google" and p["mode"] == "link" and p["aid"] == 9

    def test_bad_state(self):
        with pytest.raises(oa.OAuthError):
            oa._read_state("garbage.token.value")


class TestRedirect:
    def test_default(self):
        assert oa._redirect_uri(_req()) == "https://panel.example.com/oauth/callback"


class TestProviders:
    def test_list(self):
        assert {p["slug"] for p in oa.providers()} == {"google", "github"}
        assert oa.is_provider("google") and not oa.is_provider("vk")
