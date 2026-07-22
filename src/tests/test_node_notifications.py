"""Node health webhook notification routing."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils import notifications


NODE = {
    "uuid": "11111111-2222-3333-4444-555555555555",
    "name": "de-fra-01",
    "address": "203.0.113.10",
    "port": 2222,
    "isConnected": False,
    "lastStatusChange": "2026-07-22T10:15:29Z",
    "lastStatusMessage": "connect <ECONNREFUSED>",
    "countryCode": "DE",
}


def _settings(*, admins=(101, 202), chat_id=None, topic_id=None):
    return SimpleNamespace(
        allowed_admins=set(admins),
        notifications_chat_id=chat_id,
        get_topic_for_nodes=lambda: topic_id,
    )


def _translation(key, **kwargs):
    values = {
        "notify.node.title.node.connection_lost": "Node lost",
        "notify.node.title.node.connection_restored": "Node restored",
        "notify.node.label.address": "Address",
        "notify.node.label.status": "Status",
        "notify.node.label.reason": "Reason",
        "notify.node.label.last_status_change": "Status changed",
        "notify.node.connection.offline": "OFFLINE",
        "notify.node.connection.online": "ONLINE",
    }
    return values.get(key, key.format(**kwargs) if kwargs else key)


@pytest.fixture(autouse=True)
def reset_health_delivery_state():
    notifications._NODE_HEALTH_DELIVERIES.clear()
    notifications._NODE_HEALTH_LOCKS.clear()
    yield
    notifications._NODE_HEALTH_DELIVERIES.clear()
    notifications._NODE_HEALTH_LOCKS.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("wrapped", [False, True])
async def test_connection_lost_dms_all_admins_without_notification_chat(wrapped):
    node_data = {"response": NODE} if wrapped else NODE
    send_card = AsyncMock(return_value=True)

    with patch.object(notifications, "get_settings", return_value=_settings()), \
         patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch"), \
         patch.object(notifications, "tr", side_effect=_translation):
        await notifications.send_node_notification(
            bot=MagicMock(),
            event="node.connection_lost",
            node_data=node_data,
        )

    assert {call.args[1]["chat_id"] for call in send_card.await_args_list} == {101, 202}
    assert all("message_thread_id" not in call.args[1] for call in send_card.await_args_list)
    text = send_card.await_args_list[0].args[1]["text"]
    assert "OFFLINE" in text
    assert "connect &lt;ECONNREFUSED&gt;" in text
    assert "2026-07-22 10:15" in text


@pytest.mark.asyncio
async def test_health_transition_deduplicates_but_allows_recovery_and_new_outage():
    send_card = AsyncMock(return_value=True)
    restored = {
        **NODE,
        "isConnected": True,
        "lastStatusChange": "2026-07-22T10:16:29Z",
        "lastStatusMessage": None,
    }
    outage_again = {
        **NODE,
        "lastStatusChange": "2026-07-22T10:17:29Z",
    }

    with patch.object(notifications, "get_settings", return_value=_settings()), \
         patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch") as push_dispatch, \
         patch.object(notifications, "tr", side_effect=_translation):
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)
        await notifications.send_node_notification(MagicMock(), "node.connection_restored", restored)
        await notifications.send_node_notification(MagicMock(), "node.connection_restored", restored)
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", outage_again)

    assert send_card.await_count == 6
    assert push_dispatch.call_count == 3
    assert push_dispatch.call_args_list[1].kwargs["event"] == "node.connection_restored"


@pytest.mark.asyncio
async def test_stale_outage_retry_is_suppressed_after_recovery():
    send_card = AsyncMock(return_value=True)
    restored = {
        **NODE,
        "isConnected": True,
        "lastStatusChange": "2026-07-22T10:16:29Z",
        "lastStatusMessage": None,
    }

    with patch.object(notifications, "get_settings", return_value=_settings()), \
         patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch"), \
         patch.object(notifications, "tr", side_effect=_translation):
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)
        await notifications.send_node_notification(MagicMock(), "node.connection_restored", restored)
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)

    assert send_card.await_count == 4


@pytest.mark.asyncio
async def test_concurrent_duplicate_waits_for_first_delivery():
    both_admin_sends_started = asyncio.Event()
    release_sends = asyncio.Event()
    started_count = 0

    async def delayed_send(*_args, **_kwargs):
        nonlocal started_count
        started_count += 1
        if started_count == 2:
            both_admin_sends_started.set()
        await release_sends.wait()
        return True

    send_card = AsyncMock(side_effect=delayed_send)
    with patch.object(notifications, "get_settings", return_value=_settings()), \
         patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch"), \
         patch.object(notifications, "tr", side_effect=_translation):
        first = asyncio.create_task(
            notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)
        )
        await asyncio.wait_for(both_admin_sends_started.wait(), timeout=1)
        duplicate = asyncio.create_task(
            notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)
        )
        await asyncio.sleep(0)
        assert send_card.await_count == 2
        release_sends.set()
        await asyncio.gather(first, duplicate)

    assert send_card.await_count == 2


@pytest.mark.asyncio
async def test_global_node_topic_is_preserved_and_not_duplicated_with_admin():
    send_card = AsyncMock(return_value=True)

    with patch.object(
        notifications,
        "get_settings",
        return_value=_settings(admins=(101, 101), chat_id=-100500, topic_id=77),
    ), patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch"), \
         patch.object(notifications, "tr", side_effect=_translation):
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)

    targets = {call.args[1]["chat_id"]: call.args[1] for call in send_card.await_args_list}
    assert set(targets) == {-100500, 101}
    assert targets[-100500]["message_thread_id"] == 77
    assert "message_thread_id" not in targets[101]


@pytest.mark.asyncio
async def test_admin_matching_notification_chat_receives_one_direct_message():
    send_card = AsyncMock(return_value=True)

    with patch.object(
        notifications,
        "get_settings",
        return_value=_settings(admins=(101,), chat_id=101, topic_id=77),
    ), patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch"), \
         patch.object(notifications, "tr", side_effect=_translation):
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)

    send_card.assert_awaited_once()
    assert send_card.await_args.args[1]["chat_id"] == 101
    assert "message_thread_id" not in send_card.await_args.args[1]


@pytest.mark.asyncio
async def test_regular_node_event_does_not_dm_admins():
    send_card = AsyncMock(return_value=True)

    with patch.object(
        notifications,
        "get_settings",
        return_value=_settings(chat_id=-100500, topic_id=77),
    ), patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch"), \
         patch.object(notifications, "tr", side_effect=_translation):
        await notifications.send_node_notification(MagicMock(), "node.created", NODE)

    send_card.assert_awaited_once()
    assert send_card.await_args.args[1]["chat_id"] == -100500


@pytest.mark.asyncio
async def test_failed_admin_does_not_block_others_and_only_failure_is_retried():
    send_card = AsyncMock(side_effect=[RuntimeError("blocked"), True, True])

    with patch.object(notifications, "get_settings", return_value=_settings()), \
         patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch"), \
         patch.object(notifications, "tr", side_effect=_translation):
        with pytest.raises(RuntimeError, match="101"):
            await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)

    assert [call.args[1]["chat_id"] for call in send_card.await_args_list] == [101, 202, 101]


@pytest.mark.asyncio
async def test_rejected_telegram_response_is_retried():
    send_card = AsyncMock(side_effect=[False, True, True])

    with patch.object(notifications, "get_settings", return_value=_settings()), \
         patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch"), \
         patch.object(notifications, "tr", side_effect=_translation):
        with pytest.raises(RuntimeError, match="101"):
            await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)

    assert [call.args[1]["chat_id"] for call in send_card.await_args_list] == [101, 202, 101]


@pytest.mark.asyncio
async def test_failed_group_is_retried_without_duplicating_admin_dm():
    send_card = AsyncMock(side_effect=[False, True, True])
    settings = _settings(admins=(101,), chat_id=-100500, topic_id=77)

    with patch.object(notifications, "get_settings", return_value=settings), \
         patch.object(notifications, "_send_card", send_card), \
         patch.object(notifications, "_push_dispatch"), \
         patch.object(notifications, "tr", side_effect=_translation):
        with pytest.raises(RuntimeError, match="-100500"):
            await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)
        await notifications.send_node_notification(MagicMock(), "node.connection_lost", NODE)

    assert [call.args[1]["chat_id"] for call in send_card.await_args_list] == [
        -100500,
        101,
        -100500,
    ]
