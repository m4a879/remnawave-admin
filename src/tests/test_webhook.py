"""Incoming Remnawave webhook dispatch tests."""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.services import webhook


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "is_connected"),
    [
        ("node.connection_lost", False),
        ("node.connection_restored", True),
    ],
)
async def test_node_health_webhook_reaches_telegram_dispatch(event, is_connected):
    event_timestamp = datetime.now(timezone.utc).isoformat()
    event_data = {
        "uuid": "11111111-2222-3333-4444-555555555555",
        "name": "de-fra-01",
        "address": "203.0.113.10",
        "port": 2222,
        "isConnected": is_connected,
        "lastStatusChange": datetime.now(timezone.utc).isoformat(),
        "lastStatusMessage": "connect ECONNREFUSED" if not is_connected else None,
    }
    payload = {
        "scope": "node",
        "event": event,
        "timestamp": event_timestamp,
        "data": event_data,
    }
    bot = MagicMock()
    request = MagicMock()
    request.body = AsyncMock(return_value=json.dumps(payload).encode())
    request.app.state.bot = bot

    with patch.object(webhook, "verify_webhook_secret", return_value=True), \
         patch.object(webhook.sync_service, "handle_webhook_event", new=AsyncMock(return_value=None)), \
         patch.object(webhook, "send_node_notification", new=AsyncMock()) as send_node:
        response = await webhook.remnawave_webhook(request)

    assert response.status_code == 200
    send_node.assert_awaited_once_with(
        bot=bot,
        event=event,
        node_data={"response": event_data},
        old_node_data=None,
        changes=None,
        event_timestamp=event_timestamp,
    )


@pytest.mark.asyncio
async def test_node_webhook_rejects_invalid_signature():
    request = MagicMock()
    request.body = AsyncMock(return_value=b'{}')

    with patch.object(webhook, "verify_webhook_secret", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            await webhook.remnawave_webhook(request)

    assert exc_info.value.status_code == 401
