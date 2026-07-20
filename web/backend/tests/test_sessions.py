"""Тесты сессий админов: in-memory кэш отзыва, sid в токенах, легаси-путь."""
import time

import pytest

from web.backend.core import sessions as s
from web.backend.core.security import create_access_token, create_refresh_token, decode_token


class TestRevokedCache:
    def setup_method(self):
        s._revoked.clear()

    def test_unknown_sid_not_revoked(self):
        assert s.is_session_revoked("nope") is False

    def test_empty_sid_never_revoked(self):
        assert s.is_session_revoked("") is False

    def test_marked_sid_is_revoked(self):
        sid = s.new_sid()
        s._mark_revoked_mem(sid, time.time() + 3600)
        assert s.is_session_revoked(sid) is True

    def test_expired_entry_is_ignored_and_pruned(self):
        sid = s.new_sid()
        s._mark_revoked_mem(sid, time.time() - 1)
        assert s.is_session_revoked(sid) is False
        assert sid not in s._revoked  # проверка чистит просроченную запись

    def test_new_sid_is_unique(self):
        assert s.new_sid() != s.new_sid()


class TestSidInTokens:
    def test_access_token_carries_sid(self):
        tok = create_access_token("pwd:admin", "admin", "password", sid="abc123")
        assert decode_token(tok, "access")["sid"] == "abc123"

    def test_access_token_without_sid_has_no_claim(self):
        tok = create_access_token("pwd:admin", "admin", "password")
        assert "sid" not in decode_token(tok, "access")

    def test_refresh_token_carries_sid(self):
        tok = create_refresh_token("pwd:admin", sid="xyz789")
        assert decode_token(tok, "refresh")["sid"] == "xyz789"

    def test_refresh_token_without_sid_has_no_claim(self):
        tok = create_refresh_token("pwd:admin")
        assert "sid" not in decode_token(tok, "refresh")


class TestLegacyPath:
    @pytest.mark.asyncio
    async def test_create_session_none_account_returns_none(self):
        # Легаси env-админ без account_id не трекается, БД не трогается
        assert await s.create_session(None, "42", None, "telegram", "admin") is None

    @pytest.mark.asyncio
    async def test_validate_for_refresh_no_sid_is_valid(self):
        # Токен без sid → трекинга нет, refresh проходит как раньше
        assert await s.validate_for_refresh("") is True
