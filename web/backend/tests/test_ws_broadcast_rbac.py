"""RBAC-фильтр WS-рассылки: события уходят только админам с нужным правом."""
from types import SimpleNamespace

import pytest

from web.backend.api.v2.websocket import ConnectionManager
from web.backend.api.deps import AdminUser


SUPER = AdminUser(account_id=1, role="superadmin")
LEGACY = AdminUser(account_id=None, role="admin")  # env-admin без account_id
WITH = AdminUser(account_id=2, role="admin", permissions={("violations", "view")})
WITHOUT = AdminUser(account_id=3, role="admin", permissions=set())


class FakeWS:
    def __init__(self):
        self.sent = []
        self.state = SimpleNamespace(auth_subprotocol=None)

    async def accept(self, subprotocol=None):
        pass

    async def send_text(self, data):
        self.sent.append(data)


class TestAdminCan:
    def test_no_permission_required(self):
        assert ConnectionManager._admin_can(WITHOUT, None) is True

    def test_superadmin_bypass(self):
        assert ConnectionManager._admin_can(SUPER, ("violations", "view")) is True

    def test_legacy_bypass(self):
        assert ConnectionManager._admin_can(LEGACY, ("violations", "view")) is True

    def test_scoped_with_permission(self):
        assert ConnectionManager._admin_can(WITH, ("violations", "view")) is True

    def test_scoped_without_permission(self):
        assert ConnectionManager._admin_can(WITHOUT, ("violations", "view")) is False

    def test_none_admin(self):
        assert ConnectionManager._admin_can(None, ("violations", "view")) is False


@pytest.mark.asyncio
async def test_broadcast_filters_by_permission():
    mgr = ConnectionManager()
    ok, no = FakeWS(), FakeWS()
    await mgr.connect(ok, WITH)
    await mgr.connect(no, WITHOUT)

    await mgr.broadcast({"type": "violation", "data": {}}, permission=("violations", "view"))

    assert ok.sent, "админ с правом должен получить событие"
    assert not no.sent, "админ без права не должен получить событие"


@pytest.mark.asyncio
async def test_broadcast_without_permission_reaches_all():
    mgr = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    await mgr.connect(a, WITH)
    await mgr.connect(b, WITHOUT)

    await mgr.broadcast({"type": "activity", "data": {}})  # без permission — всем

    assert a.sent and b.sent
