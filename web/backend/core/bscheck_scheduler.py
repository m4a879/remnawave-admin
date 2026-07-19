"""Авто-проверка нод через операторов РФ (bschekbot) по расписанию.

Проба ПЛАТНАЯ, поэтому есть дневной бюджет-гард (bscheck_auto_budget_daily) и
троттлинг 1 req/s (лимит bsbord). Результаты пишутся в общий журнал
(created_by='scheduler'). Опционально — алерт в Telegram на просадку БС.

Интервал не через sleep, а по времени последней авто-записи в БД: тик каждые
~5 мин проверяет, прошёл ли `interval_hours` с прошлого прогона (переживает
рестарты, не копит долг).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_SCHED_BY = "scheduler"
_TICK_SECONDS = 300
_STARTUP_DELAY = 180


def _due(last_iso, interval_h: int, now: datetime) -> bool:
    if interval_h <= 0:
        return False
    if not last_iso:
        return True
    try:
        last = datetime.fromisoformat(last_iso)
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) >= timedelta(hours=interval_h)


async def run_bscheck_tick() -> None:
    from shared.config_service import config_service  # noqa: F401 (ensures cache warm)
    from shared.database import db_service
    from web.backend.core import bscheck as bs

    cfg = bs.read_schedule()
    if not cfg["enabled"] or cfg["interval_hours"] <= 0:
        return
    if not bs.is_configured():
        logger.info("bscheck auto: включено, но токен не настроен — пропуск")
        return

    now = datetime.now(timezone.utc)
    last = await db_service.get_bscheck_last_run(_SCHED_BY)
    if not _due(last, cfg["interval_hours"], now):
        return

    budget = cfg["budget_daily"]
    spent = await db_service.get_bscheck_spent_today(_SCHED_BY)
    if budget > 0 and spent >= budget:
        logger.info("bscheck auto: дневной бюджет исчерпан (%d/%d), пропуск", spent, budget)
        return

    dpi = cfg["dpi"] if cfg["dpi"] in ("on", "any") else "on"
    operators = cfg["operators"]
    node_filter = set(cfg["nodes"])
    alert = cfg["alert"]
    probes = {"icmp": True, "tcp": True, "sni": False}

    rows = await db_service.get_all_nodes()
    checked = 0
    for n in rows:
        uuid = n.get("uuid")
        if node_filter and uuid not in node_filter:
            continue
        ip = n.get("agent_ip") or n.get("address")
        if not ip:
            continue
        if budget > 0 and spent >= budget:
            logger.info("bscheck auto: бюджет достигнут на середине (%d), стоп", spent)
            break

        target = f"{ip}:443"
        prev = await db_service.get_last_bscheck(uuid)
        try:
            result = await bs.probe({"target": target, "operators": operators, "probes": probes, "dpi": dpi})
        except bs.BscheckError as e:
            logger.warning("bscheck auto: проба %s не удалась: %s", ip, e)
            await asyncio.sleep(1)
            continue

        summary = bs.summarize(result, target)
        spent += int(summary.get("cost_credits") or 0)
        await db_service.save_bscheck(
            uuid, summary["passed"], summary["total"], summary.get("cost_credits"),
            {"summary": summary, "raw": result}, created_by=_SCHED_BY, target=ip)
        checked += 1

        if alert and isinstance(prev, dict) and isinstance(prev.get("result"), dict):
            prev_passed = (prev["result"].get("summary") or {}).get("passed")
            if isinstance(prev_passed, int) and summary["passed"] < prev_passed:
                try:
                    from web.backend.core.notification_service import notify_bscheck_drop
                    await notify_bscheck_drop(
                        n.get("name") or ip, ip, summary["passed"], summary["total"], prev_passed)
                except Exception as e:  # noqa: BLE001
                    logger.debug("bscheck auto: алерт не отправлен: %s", e)

        await asyncio.sleep(1)  # троттлинг bsbord (1 req/s)

    if checked:
        logger.info("bscheck auto: проверено %d нод, потрачено≈%d кредитов сегодня", checked, spent)


async def bscheck_scheduler_loop() -> None:
    await asyncio.sleep(_STARTUP_DELAY)
    while True:
        try:
            await run_bscheck_tick()
        except Exception as exc:  # noqa: BLE001
            logger.warning("bscheck scheduler tick failed: %s", exc)
        await asyncio.sleep(_TICK_SECONDS)
