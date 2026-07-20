"""Tests for WebSocket handshake authentication (extract_ws_token) + Origin/re-auth."""
import time
from types import SimpleNamespace

import pytest

from web.backend.api.deps import (
    extract_ws_token,
    WS_AUTH_SUBPROTOCOL,
    ws_origin_allowed,
    ws_auth_invalid,
)
from web.backend.core.security import create_access_token
from web.backend.core.token_blacklist import token_blacklist
from web.backend.core import sessions


class FakeWsState:
    """Fake websocket with headers + .state (для ws_origin_allowed / ws_auth_invalid)."""

    def __init__(self, headers=None, auth_token=...):
        self.headers = headers or {}
        self.state = SimpleNamespace()
        if auth_token is not ...:
            self.state.auth_token = auth_token


class FakeWebSocket:
    """Minimal stand-in: extract_ws_token uses headers/cookies/query_params."""

    def __init__(self, headers=None, query_params=None, cookies=None):
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.cookies = cookies or {}


class TestExtractWsToken:
    def test_subprotocol_token(self):
        """Токен из Sec-WebSocket-Protocol — основной механизм."""
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token, my.jwt.token"}
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "my.jwt.token"
        assert subprotocol == WS_AUTH_SUBPROTOCOL

    def test_subprotocol_whitespace_tolerant(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": " access-token ,  my.jwt.token "}
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "my.jwt.token"
        assert subprotocol == WS_AUTH_SUBPROTOCOL

    def test_query_fallback(self):
        """Старые клиенты с ?token= продолжают работать (deprecated)."""
        ws = FakeWebSocket(query_params={"token": "legacy.jwt"})
        token, subprotocol = extract_ws_token(ws)
        assert token == "legacy.jwt"
        assert subprotocol is None

    def test_subprotocol_wins_over_query(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token, header.jwt"},
            query_params={"token": "query.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "header.jwt"
        assert subprotocol == WS_AUTH_SUBPROTOCOL

    def test_foreign_subprotocol_falls_back_to_query(self):
        """Чужой subprotocol (не access-token) не трактуется как токен."""
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "graphql-ws"},
            query_params={"token": "query.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "query.jwt"
        assert subprotocol is None

    def test_marker_without_token_falls_back(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token"},
            query_params={"token": "query.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "query.jwt"
        assert subprotocol is None

    def test_empty_token_part_falls_back(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token, "},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token is None
        assert subprotocol is None

    def test_no_auth_at_all(self):
        token, subprotocol = extract_ws_token(FakeWebSocket())
        assert token is None
        assert subprotocol is None

    def test_cookie_source(self):
        """HttpOnly cookie rw_access — источник для cookie-аутентификации."""
        ws = FakeWebSocket(cookies={"rw_access": "cookie.jwt"})
        token, subprotocol = extract_ws_token(ws)
        assert token == "cookie.jwt"
        assert subprotocol is None

    def test_subprotocol_wins_over_cookie(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token, header.jwt"},
            cookies={"rw_access": "cookie.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "header.jwt"
        assert subprotocol == WS_AUTH_SUBPROTOCOL

    def test_cookie_wins_over_query(self):
        ws = FakeWebSocket(
            cookies={"rw_access": "cookie.jwt"},
            query_params={"token": "query.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "cookie.jwt"
        assert subprotocol is None


class TestWsOriginAllowed:
    def test_no_origin_native_client(self):
        # Мобильное приложение / агент Origin не шлют — пропускаем
        assert ws_origin_allowed(FakeWsState()) is True

    def test_same_origin(self):
        ws = FakeWsState(headers={"origin": "https://panel.example.com", "host": "panel.example.com"})
        assert ws_origin_allowed(ws) is True

    def test_cross_origin_blocked(self):
        ws = FakeWsState(headers={"origin": "https://evil.com", "host": "panel.example.com"})
        assert ws_origin_allowed(ws) is False

    def test_configured_cors_origin(self):
        # http://localhost:3000 — в дефолтном WEB_CORS_ORIGINS
        ws = FakeWsState(headers={"origin": "http://localhost:3000", "host": "unrelated"})
        assert ws_origin_allowed(ws) is True


class TestWsAuthInvalid:
    def test_no_token_stashed(self):
        assert ws_auth_invalid(FakeWsState()) is None

    def test_valid_token(self):
        tok = create_access_token("pwd:ok", "ok", "password")
        assert ws_auth_invalid(FakeWsState(auth_token=tok)) is None

    def test_garbage_token_expired(self):
        assert ws_auth_invalid(FakeWsState(auth_token="not.a.jwt")) == "token expired"

    def test_blacklisted_token(self):
        tok = create_access_token("pwd:bl", "bl", "password")
        token_blacklist.add(tok, time.time() + 3600)
        assert ws_auth_invalid(FakeWsState(auth_token=tok)) == "token revoked"

    def test_session_revoked(self):
        sid = sessions.new_sid()
        tok = create_access_token("pwd:sess", "sess", "password", sid=sid)
        sessions._mark_revoked_mem(sid, time.time() + 3600)
        assert ws_auth_invalid(FakeWsState(auth_token=tok)) == "session revoked"
