"""Tests for web.backend.core.mail.submission_server module."""
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from web.backend.core.mail.submission_server import (
    _hash_password,
    hash_password_for_storage,
    verify_password,
    SubmissionAuthenticator,
    SubmissionHandler,
    _CRED_COUNTER,
)

MODULE = "web.backend.core.mail.submission_server"


@pytest.fixture(autouse=True)
def _clear_counters():
    _CRED_COUNTER.clear()
    yield
    _CRED_COUNTER.clear()


# ── _hash_password ───────────────────────────────────────────


class TestHashPassword:
    def test_returns_hex_string(self):
        result = _hash_password("mypass", "mysalt")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex

    def test_deterministic(self):
        a = _hash_password("pass", "salt")
        b = _hash_password("pass", "salt")
        assert a == b

    def test_different_salt_different_hash(self):
        a = _hash_password("pass", "salt1")
        b = _hash_password("pass", "salt2")
        assert a != b

    def test_different_password_different_hash(self):
        a = _hash_password("pass1", "salt")
        b = _hash_password("pass2", "salt")
        assert a != b

    def test_matches_expected(self):
        expected = hashlib.sha256("mysalt:mypass".encode()).hexdigest()
        assert _hash_password("mypass", "mysalt") == expected


# ── hash_password_for_storage ────────────────────────────────


class TestHashPasswordForStorage:
    def test_format(self):
        result = hash_password_for_storage("password123")
        assert "$" in result
        salt, hashed = result.split("$", 1)
        assert len(salt) == 32  # token_hex(16) -> 32 hex chars
        assert len(hashed) == 64  # SHA-256 hex

    def test_unique_salt_each_call(self):
        a = hash_password_for_storage("same")
        b = hash_password_for_storage("same")
        assert a != b  # different salt


# ── verify_password ──────────────────────────────────────────


class TestVerifyPassword:
    def test_correct_password(self):
        stored = hash_password_for_storage("secret")
        assert verify_password("secret", stored) is True

    def test_wrong_password(self):
        stored = hash_password_for_storage("secret")
        assert verify_password("wrong", stored) is False

    def test_invalid_format_no_dollar(self):
        assert verify_password("pass", "no_dollar_sign") is False

    def test_empty_password(self):
        stored = hash_password_for_storage("")
        assert verify_password("", stored) is True
        assert verify_password("notempty", stored) is False


# ── SubmissionAuthenticator ──────────────────────────────────


class TestSubmissionAuthenticator:
    def _make_auth_data(self, login: str, password: str):
        from aiosmtpd.smtp import LoginPassword
        return LoginPassword(login=login.encode(), password=password.encode())

    def _make_session(self, peer=("127.0.0.1", 12345)):
        session = MagicMock()
        session.peer = peer
        return session

    def test_auth_success(self):
        auth = SubmissionAuthenticator()
        stored = hash_password_for_storage("mypass")
        auth._credentials = {
            "user1": {
                "id": 1,
                "username": "user1",
                "password_hash": stored,
                "is_active": True,
                "max_send_per_hour": 100,
                "allowed_from_domains": [],
            }
        }

        session = self._make_session()
        auth_data = self._make_auth_data("user1", "mypass")

        with patch.object(auth, '_update_last_login', new_callable=AsyncMock):
            result = auth(None, session, None, "LOGIN", auth_data)

        assert result.success is True

    def test_auth_unknown_user(self):
        auth = SubmissionAuthenticator()
        auth._credentials = {}

        session = self._make_session()
        auth_data = self._make_auth_data("unknown", "pass")
        result = auth(None, session, None, "LOGIN", auth_data)

        assert result.success is False

    def test_auth_wrong_password(self):
        auth = SubmissionAuthenticator()
        stored = hash_password_for_storage("correct")
        auth._credentials = {
            "user1": {
                "id": 1,
                "username": "user1",
                "password_hash": stored,
                "is_active": True,
                "max_send_per_hour": 100,
                "allowed_from_domains": [],
            }
        }

        session = self._make_session()
        auth_data = self._make_auth_data("user1", "wrong")
        result = auth(None, session, None, "LOGIN", auth_data)

        assert result.success is False

    def test_auth_rate_limit(self):
        auth = SubmissionAuthenticator()
        stored = hash_password_for_storage("pass")
        auth._credentials = {
            "user1": {
                "id": 1,
                "username": "user1",
                "password_hash": stored,
                "is_active": True,
                "max_send_per_hour": 2,
                "allowed_from_domains": [],
            }
        }

        # Simulate already at rate limit
        _CRED_COUNTER[1]["count"] = 2
        _CRED_COUNTER[1]["reset_at"] = datetime.now(timezone.utc) + timedelta(hours=1)

        session = self._make_session()
        auth_data = self._make_auth_data("user1", "pass")
        result = auth(None, session, None, "LOGIN", auth_data)

        assert result.success is False

    def test_auth_rate_limit_resets(self):
        auth = SubmissionAuthenticator()
        stored = hash_password_for_storage("pass")
        auth._credentials = {
            "user1": {
                "id": 1,
                "username": "user1",
                "password_hash": stored,
                "is_active": True,
                "max_send_per_hour": 100,
                "allowed_from_domains": [],
            }
        }

        # Simulate expired rate limit
        _CRED_COUNTER[1]["count"] = 999
        _CRED_COUNTER[1]["reset_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)

        session = self._make_session()
        auth_data = self._make_auth_data("user1", "pass")

        with patch.object(auth, '_update_last_login', new_callable=AsyncMock):
            result = auth(None, session, None, "LOGIN", auth_data)

        assert result.success is True

    def test_auth_non_login_password(self):
        auth = SubmissionAuthenticator()
        session = self._make_session()
        result = auth(None, session, None, "PLAIN", "not-a-LoginPassword")
        assert result.success is False

    def test_auth_sets_session_attrs(self):
        auth = SubmissionAuthenticator()
        stored = hash_password_for_storage("pass")
        auth._credentials = {
            "testuser": {
                "id": 42,
                "username": "testuser",
                "password_hash": stored,
                "is_active": True,
                "max_send_per_hour": 50,
                "allowed_from_domains": ["example.com"],
            }
        }

        session = self._make_session()
        auth_data = self._make_auth_data("testuser", "pass")

        with patch.object(auth, '_update_last_login', new_callable=AsyncMock):
            auth(None, session, None, "LOGIN", auth_data)

        assert session.smtp_credential_id == 42
        assert session.smtp_username == "testuser"
        assert session.smtp_max_per_hour == 50
        assert session.smtp_allowed_domains == ["example.com"]


# ── SubmissionHandler ────────────────────────────────────────


class TestSubmissionHandler:
    @pytest.mark.asyncio
    async def test_handle_ehlo(self):
        handler = SubmissionHandler()
        session = MagicMock()
        responses = ["250-remnawave", "250 OK"]
        result = await handler.handle_EHLO(None, session, None, "client.example.com", responses)
        assert result == responses
        assert session.host_name == "client.example.com"

    @pytest.mark.asyncio
    async def test_handle_rcpt_valid(self):
        handler = SubmissionHandler()
        session = MagicMock()
        envelope = MagicMock()
        envelope.rcpt_tos = []
        result = await handler.handle_RCPT(None, session, envelope, "user@example.com", [])
        assert result == "250 OK"
        assert "user@example.com" in envelope.rcpt_tos

    @pytest.mark.asyncio
    async def test_handle_rcpt_no_at(self):
        handler = SubmissionHandler()
        session = MagicMock()
        envelope = MagicMock()
        envelope.rcpt_tos = []
        result = await handler.handle_RCPT(None, session, envelope, "invalid-address", [])
        assert "550" in result

    @pytest.mark.asyncio
    async def test_handle_rcpt_empty(self):
        handler = SubmissionHandler()
        session = MagicMock()
        envelope = MagicMock()
        envelope.rcpt_tos = []
        result = await handler.handle_RCPT(None, session, envelope, "", [])
        assert "550" in result

    @pytest.mark.asyncio
    async def test_handle_data_enqueues(self):
        handler = SubmissionHandler()
        session = MagicMock()
        session.smtp_credential_id = 1
        session.smtp_username = "user"
        session.smtp_allowed_domains = []

        envelope = MagicMock()
        envelope.mail_from = "sender@example.com"
        envelope.rcpt_tos = ["recipient@example.com"]
        envelope.content = (
            b"From: sender@example.com\r\n"
            b"To: recipient@example.com\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Hello world"
        )

        mock_queue = AsyncMock()
        mock_queue.enqueue.return_value = 1

        with patch("web.backend.core.mail.outbound_queue.outbound_queue", mock_queue):
            result = await handler.handle_DATA(None, session, envelope)

        assert "250" in result
        mock_queue.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_data_domain_restriction(self):
        handler = SubmissionHandler()
        session = MagicMock()
        session.smtp_credential_id = 1
        session.smtp_username = "user"
        session.smtp_allowed_domains = ["allowed.com"]

        envelope = MagicMock()
        envelope.mail_from = "sender@forbidden.com"
        envelope.rcpt_tos = ["recipient@example.com"]
        envelope.content = b"From: sender@forbidden.com\r\nSubject: X\r\n\r\nBody"

        result = await handler.handle_DATA(None, session, envelope)
        assert "550" in result

    @pytest.mark.asyncio
    async def test_handle_data_452_when_nothing_queued(self):
        """If the outbound queue rejects everything (rate limit / transient
        error), the client must get a 4xx — never a silent 250 that makes the
        mail look 'sent' while it was dropped."""
        handler = SubmissionHandler()
        session = MagicMock()
        session.smtp_credential_id = 1
        session.smtp_username = "user"
        session.smtp_allowed_domains = []

        envelope = MagicMock()
        envelope.mail_from = "sender@example.com"
        envelope.rcpt_tos = ["recipient@example.com"]
        envelope.content = (
            b"From: sender@example.com\r\n"
            b"To: recipient@example.com\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Hello world"
        )

        mock_queue = AsyncMock()
        mock_queue.enqueue.return_value = None  # queue refused (rate limit)

        with patch("web.backend.core.mail.outbound_queue.outbound_queue", mock_queue):
            result = await handler.handle_DATA(None, session, envelope)

        assert result.startswith("452")

    @pytest.mark.asyncio
    async def test_handle_data_250_on_partial(self):
        """Some recipients queued, some rejected → keep 250 (avoid duplicate
        resends of the ones that did go through)."""
        handler = SubmissionHandler()
        session = MagicMock()
        session.smtp_credential_id = 1
        session.smtp_username = "user"
        session.smtp_allowed_domains = []

        envelope = MagicMock()
        envelope.mail_from = "sender@example.com"
        envelope.rcpt_tos = ["a@example.com", "b@example.com"]
        envelope.content = b"From: sender@example.com\r\nSubject: X\r\n\r\nBody"

        mock_queue = AsyncMock()
        mock_queue.enqueue.side_effect = [1, None]  # first ok, second rejected

        with patch("web.backend.core.mail.outbound_queue.outbound_queue", mock_queue):
            result = await handler.handle_DATA(None, session, envelope)

        assert result.startswith("250")
