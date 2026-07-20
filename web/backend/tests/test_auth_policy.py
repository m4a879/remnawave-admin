"""Тесты политики метода входа: parse/serialize/method_allowed."""
import json

from web.backend.core.auth_policy import parse_methods, serialize_methods, method_allowed, AUTH_METHODS


class TestParse:
    def test_none_and_empty(self):
        assert parse_methods(None) is None
        assert parse_methods("") is None
        assert parse_methods("   ") is None
        assert parse_methods("[]") is None

    def test_json_string(self):
        assert parse_methods('["password","passkey"]') == ["password", "passkey"]

    def test_list_input(self):
        assert parse_methods(["oauth", "telegram"]) == ["telegram", "oauth"]  # канонический порядок

    def test_drops_unknown(self):
        assert parse_methods('["password","bogus"]') == ["password"]

    def test_broken_json(self):
        assert parse_methods("{not json") is None

    def test_all_unknown_is_none(self):
        assert parse_methods('["nope"]') is None


class TestSerialize:
    def test_none_empty(self):
        assert serialize_methods(None) is None
        assert serialize_methods([]) is None

    def test_all_methods_stored_as_none(self):
        # все методы разрешены → политика не нужна → NULL
        assert serialize_methods(list(AUTH_METHODS)) is None

    def test_subset_is_json(self):
        raw = serialize_methods(["passkey", "password"])
        assert json.loads(raw) == ["password", "passkey"]  # канонический порядок

    def test_drops_unknown(self):
        raw = serialize_methods(["password", "bogus"])
        assert json.loads(raw) == ["password"]


class TestMethodAllowed:
    def test_no_account(self):
        assert method_allowed(None, "password") is True

    def test_no_policy(self):
        assert method_allowed({"allowed_auth_methods": None}, "telegram") is True

    def test_restricted_allows_listed(self):
        acc = {"allowed_auth_methods": '["passkey"]'}
        assert method_allowed(acc, "passkey") is True

    def test_restricted_blocks_unlisted(self):
        acc = {"allowed_auth_methods": '["passkey"]'}
        assert method_allowed(acc, "password") is False
        assert method_allowed(acc, "telegram") is False
