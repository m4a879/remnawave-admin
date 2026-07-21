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
        assert {p["slug"] for p in oa.providers()} == {"google", "github", "oidc"}
        assert oa.is_provider("google") and not oa.is_provider("vk")


class TestGenericOidc:
    """Generic OIDC: issuer обязателен, discovery кэшируется, userinfo по sub."""

    def _cfg(self, monkeypatch, values):
        from shared import config_service as cs
        monkeypatch.setattr(cs.config_service, "get",
                            lambda key, default=None: values.get(key, default))

    def test_not_configured_without_issuer(self, monkeypatch):
        self._cfg(monkeypatch, {"oauth_oidc_client_id": "cid"})
        monkeypatch.setattr(oa, "get_client_secret", lambda p: "sec")
        assert not oa.is_configured("oidc")

    def test_configured_with_issuer(self, monkeypatch):
        self._cfg(monkeypatch, {
            "oauth_oidc_client_id": "cid",
            "oauth_oidc_issuer": "https://id.example.com/",
        })
        monkeypatch.setattr(oa, "get_client_secret", lambda p: "sec")
        assert oa.is_configured("oidc")
        assert oa.get_oidc_issuer() == "https://id.example.com"  # хвостовой / срезан

    def test_display_name_from_settings(self, monkeypatch):
        self._cfg(monkeypatch, {"oauth_oidc_name": "PocketID"})
        assert oa.provider_display_name("oidc") == "PocketID"
        self._cfg(monkeypatch, {})
        assert oa.provider_display_name("oidc") == oa.OIDC_DEFAULT_NAME

    @pytest.mark.asyncio
    async def test_discovery_cached_and_used_in_authorize(self, monkeypatch):
        self._cfg(monkeypatch, {
            "oauth_oidc_client_id": "cid",
            "oauth_oidc_issuer": "https://id.example.com",
        })
        monkeypatch.setattr(oa, "get_client_secret", lambda p: "sec")
        oa._discovery_cache.clear()

        calls = {"n": 0}

        class _Resp:
            status_code = 200
            def json(self):
                return {
                    "authorization_endpoint": "https://id.example.com/authorize",
                    "token_endpoint": "https://id.example.com/token",
                    "userinfo_endpoint": "https://id.example.com/userinfo",
                }

        class _Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, headers=None):
                calls["n"] += 1
                assert url.endswith("/.well-known/openid-configuration")
                return _Resp()

        monkeypatch.setattr(oa.httpx, "AsyncClient", _Client)
        url = await oa.build_authorize_url(_req(), "oidc", "login", None)
        assert url.startswith("https://id.example.com/authorize?")
        assert "client_id=cid" in url and "scope=openid+profile+email" in url
        # повторный вызов — из кэша, без второго запроса discovery
        await oa.build_authorize_url(_req(), "oidc", "login", None)
        assert calls["n"] == 1
        oa._discovery_cache.clear()

    @pytest.mark.asyncio
    async def test_userinfo_maps_oidc_claims(self, monkeypatch):
        oa._discovery_cache["https://id.example.com"] = (
            9e18, {"authorize": "a", "token": "t",
                   "userinfo": "https://id.example.com/userinfo"})
        self._cfg(monkeypatch, {"oauth_oidc_issuer": "https://id.example.com"})

        class _Resp:
            status_code = 200
            def json(self):
                return {"sub": "u-42", "email": "a@b.c", "preferred_username": "vasya"}

        class _Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, headers=None):
                assert url == "https://id.example.com/userinfo"
                assert headers["Authorization"] == "Bearer tok"
                return _Resp()

        monkeypatch.setattr(oa.httpx, "AsyncClient", _Client)
        info = await oa._userinfo("oidc", "tok")
        assert info == {"external_id": "u-42", "email": "a@b.c", "name": "vasya"}
        oa._discovery_cache.clear()

    @pytest.mark.asyncio
    async def test_authorize_fails_without_config(self, monkeypatch):
        self._cfg(monkeypatch, {})
        monkeypatch.setattr(oa, "get_client_secret", lambda p: "")
        with pytest.raises(oa.OAuthError):
            await oa.build_authorize_url(_req(), "oidc", "login", None)


class TestBuildAuthorizeAsync:
    """build_authorize_url стал async — статические провайдеры работают как раньше."""

    @pytest.mark.asyncio
    async def test_google_url(self, monkeypatch):
        monkeypatch.setattr(oa, "get_client_id", lambda p: "gcid")
        monkeypatch.setattr(oa, "get_client_secret", lambda p: "gsec")
        url = await oa.build_authorize_url(_req(), "google", "login", None)
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "prompt=select_account" in url
