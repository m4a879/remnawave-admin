"""Prometheus metrics for the web backend.

Exports a `/metrics` endpoint (text format 0.0.4) for external scrape
by Prometheus / VictoriaMetrics. Includes HTTP middleware metrics and
panel-specific gauges refreshed by a background updater.

Cardinality note: HTTP path label uses the route *pattern* (e.g.
`/api/v2/users/{user_id}`) — never the raw URL — so user UUIDs and
similar IDs don't blow up label sets.

Counters fired from app code (collector, violation pipeline, etc.) are
defined here too; just `import ... from web.backend.core.metrics` and
call `.inc()` / `.labels(...).inc()`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from shared.db_schema import USERS_TABLE, NODES_TABLE, VIOLATIONS_TABLE, \
    USER_CONNECTIONS_TABLE, USER_HWID_DEVICES_TABLE, SYNC_METADATA_TABLE, \
    SUBSCRIPTION_REQUEST_HISTORY_TABLE
from shared.db_query import select_sql

logger = logging.getLogger(__name__)

# ── HTTP metrics ─────────────────────────────────────────────────

HTTP_REQUESTS_TOTAL = Counter(
    "panel_http_requests_total",
    "Total HTTP requests handled by the panel backend.",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "panel_http_request_duration_seconds",
    "HTTP request handling latency in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "panel_http_requests_in_progress",
    "Number of HTTP requests currently being processed.",
    ["method"],
)

# ── Panel-state gauges (refreshed by updater) ────────────────────

PANEL_ONLINE_USERS = Gauge(
    "panel_online_users",
    "Unique users seen in user_connections in the last 2 minutes.",
)

PANEL_TOTAL_USERS = Gauge(
    "panel_total_users",
    "Total users in panel DB.",
)

PANEL_ACTIVE_USERS = Gauge(
    "panel_active_users",
    "Users with status='ACTIVE'.",
)

PANEL_TOTAL_NODES = Gauge(
    "panel_total_nodes",
    "Total nodes in panel DB.",
)

PANEL_ONLINE_NODES = Gauge(
    "panel_online_nodes",
    "Nodes that are connected and not disabled.",
)

PANEL_VIOLATIONS_OPEN = Gauge(
    "panel_violations_open",
    "Violations with status='ACTIVE'.",
)

PANEL_DB_POOL_SIZE = Gauge(
    "panel_db_pool_size",
    "Configured PostgreSQL pool size.",
)

PANEL_DB_POOL_USED = Gauge(
    "panel_db_pool_used",
    "Currently checked-out connections from the PostgreSQL pool.",
)

# Users breakdown ─ refreshed by updater
PANEL_USERS_BY_STATUS = Gauge(
    "panel_users_by_status",
    "Users grouped by status (ACTIVE, DISABLED, LIMITED, EXPIRED).",
    ["status"],
)

PANEL_USERS_EXPIRING_SOON = Gauge(
    "panel_users_expiring_soon",
    "Users whose subscription expires in the next 7 days.",
)

PANEL_USERS_TRAFFIC_LIMIT_REACHED = Gauge(
    "panel_users_traffic_limit_reached",
    "Users who hit their traffic limit (used >= limit, limit > 0).",
)

PANEL_USERS_HWID_LIMIT_REACHED = Gauge(
    "panel_users_hwid_limit_reached",
    "Users with devices count >= hwid_device_limit (limit > 0).",
)

PANEL_USERS_CREATED = Gauge(
    "panel_users_created",
    "Users created within the rolling window.",
    ["window"],  # 24h, 7d, 30d
)

PANEL_USERS_EXPIRING = Gauge(
    "panel_users_expiring",
    "Users whose subscription expires within the rolling window.",
    ["window"],  # 1d, 7d, 30d
)

PANEL_USERS_BY_TRAFFIC_BUCKET = Gauge(
    "panel_users_by_traffic_bucket",
    "Users grouped by cumulative used_traffic_bytes bucket.",
    ["bucket"],  # lt_10gb, 10_100gb, 100gb_1tb, gt_1tb
)

PANEL_HWID_DEVICES_PER_USER_AVG = Gauge(
    "panel_hwid_devices_per_user_avg",
    "Average HWID devices per user (total devices / users with >=1 device).",
)

PANEL_SUBSCRIPTION_REQUESTS = Gauge(
    "panel_subscription_requests",
    "Subscription fetch requests recorded within the window.",
    ["window"],  # 1h, 24h
)

PANEL_ACTIVE_CONNECTIONS = Gauge(
    "panel_active_connections",
    "Open rows in user_connections (disconnected_at IS NULL).",
)

# HWID
PANEL_HWID_DEVICES_TOTAL = Gauge(
    "panel_hwid_devices_total",
    "Total HWID devices registered across all users.",
)

PANEL_HWID_BY_PLATFORM = Gauge(
    "panel_hwid_devices_by_platform",
    "HWID devices grouped by platform.",
    ["platform"],
)

# Per-node — cardinality ~tens of nodes, safe
PANEL_NODE_CPU_USAGE = Gauge(
    "panel_node_cpu_usage_percent",
    "Per-node CPU utilization, 0-100.",
    ["node"],
)

PANEL_NODE_MEMORY_USAGE = Gauge(
    "panel_node_memory_usage_percent",
    "Per-node memory utilization, 0-100.",
    ["node"],
)

PANEL_NODE_DISK_USAGE = Gauge(
    "panel_node_disk_usage_percent",
    "Per-node disk utilization, 0-100.",
    ["node"],
)

PANEL_NODE_LAST_SEEN_SECONDS = Gauge(
    "panel_node_last_seen_seconds",
    "Seconds since the node-agent last reported metrics.",
    ["node"],
)

PANEL_NODE_TRAFFIC_USED_BYTES = Gauge(
    "panel_node_traffic_used_bytes",
    "Per-node cumulative traffic used (panel-reported).",
    ["node"],
)

PANEL_NODE_CONNECTED = Gauge(
    "panel_node_connected",
    "1 if node is connected and not disabled, else 0.",
    ["node"],
)

PANEL_NODE_CPU_CORES = Gauge(
    "panel_node_cpu_cores",
    "Per-node CPU cores reported by agent.",
    ["node"],
)

PANEL_NODE_MEMORY_TOTAL_BYTES = Gauge(
    "panel_node_memory_total_bytes",
    "Per-node total RAM (bytes).",
    ["node"],
)

PANEL_NODE_MEMORY_USED_BYTES = Gauge(
    "panel_node_memory_used_bytes",
    "Per-node used RAM (bytes).",
    ["node"],
)

PANEL_NODE_DISK_TOTAL_BYTES = Gauge(
    "panel_node_disk_total_bytes",
    "Per-node total disk space (bytes).",
    ["node"],
)

PANEL_NODE_DISK_USED_BYTES = Gauge(
    "panel_node_disk_used_bytes",
    "Per-node used disk space (bytes).",
    ["node"],
)

PANEL_NODE_DISK_READ_BPS = Gauge(
    "panel_node_disk_read_bytes_per_second",
    "Per-node current disk read speed.",
    ["node"],
)

PANEL_NODE_DISK_WRITE_BPS = Gauge(
    "panel_node_disk_write_bytes_per_second",
    "Per-node current disk write speed.",
    ["node"],
)

PANEL_NODE_UPTIME_SECONDS = Gauge(
    "panel_node_uptime_seconds",
    "Per-node uptime since last boot, reported by agent.",
    ["node"],
)

# Sync lag
PANEL_SYNC_LAG_SECONDS = Gauge(
    "panel_sync_lag_seconds",
    "Seconds since the last successful sync of each kind.",
    ["kind"],
)

# Anti-abuse
PANEL_VIOLATIONS_BY_ACTION = Gauge(
    "panel_violations_by_action",
    "Open violations grouped by recommended_action.",
    ["action"],
)

PANEL_TORRENT_EVENTS_24H = Gauge(
    "panel_torrent_events_24h",
    "Torrent events detected in the last 24 hours.",
)

# ── App event counters ───────────────────────────────────────────
# Реальные объявления Counter'ов в shared/metrics.py — здесь только
# re-export, чтобы внешний код мог импортировать привычно из этого
# модуля, а shared/-код не зависел от web/backend/.
from shared.metrics import (  # noqa: F401
    COLLECTOR_BATCHES_RECEIVED,
    COLLECTOR_BATCHES_REJECTED,
    COLLECTOR_CONNECTIONS_PROCESSED,
    NOTIFICATIONS_FAILED,
    NOTIFICATIONS_SENT,
    SYNC_RUNS,
    VIOLATIONS_DETECTED,
)


# ── HTTP middleware ──────────────────────────────────────────────


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records HTTP RPS / latency / in-flight for every matched route."""

    async def dispatch(self, request: Request, call_next):
        method = request.method
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            raise
        finally:
            duration = time.perf_counter() - start
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            path = _route_template(request)
            HTTP_REQUESTS_TOTAL.labels(
                method=method, path=path, status=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, path=path,
            ).observe(duration)


def _route_template(request: Request) -> str:
    """Return the route pattern (e.g. /api/v2/users/{user_id}) or 'other'.

    Using the raw URL would create a label per user UUID and explode cardinality.
    """
    route = request.scope.get("route")
    if route is None:
        # Unmatched URL or middleware ran before routing — collapse to a constant.
        return "other"
    path = getattr(route, "path", None) or getattr(route, "path_format", None)
    return path or "other"


# ── /metrics endpoint helpers ────────────────────────────────────


def metrics_auth_token() -> Optional[str]:
    token = os.getenv("METRICS_AUTH_TOKEN", "").strip()
    return token or None


def render_metrics() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics response."""
    return generate_latest(), CONTENT_TYPE_LATEST


# ── Background gauge updater ─────────────────────────────────────


class GaugeUpdater:
    """Periodically refreshes panel_* gauges from the database."""

    def __init__(self, interval_seconds: int = 15):
        self.interval = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Prometheus gauge updater started (every %ds)", self.interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Prometheus gauge updater stopped")

    async def _loop(self) -> None:
        # initial small delay so DB warms up
        await asyncio.sleep(5)
        while self._running:
            try:
                await self._refresh()
            except Exception as e:
                logger.warning("Gauge refresh failed: %s", e)
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break

    async def _refresh(self) -> None:
        from shared.database import db_service
        if not db_service.is_connected:
            return

        async with db_service.acquire() as conn:
            # Aggregates — single round-trip
            row = await conn.fetchrow(
                f"""
                SELECT
                    (SELECT COUNT(DISTINCT user_uuid) FROM {USER_CONNECTIONS_TABLE}
                     WHERE user_uuid IS NOT NULL
                       AND connected_at >= NOW() - INTERVAL '2 minutes'
                    ) AS online_users,
                    (SELECT COUNT(*) FROM {USERS_TABLE}) AS total_users,
                    (SELECT COUNT(*) FROM {USERS_TABLE} WHERE UPPER(status) = 'ACTIVE') AS active_users,
                    (SELECT COUNT(*) FROM {NODES_TABLE}) AS total_nodes,
                    (SELECT COUNT(*) FROM {NODES_TABLE}
                     WHERE is_connected = true AND NOT is_disabled
                    ) AS online_nodes,
                    (SELECT COUNT(*) FROM {VIOLATIONS_TABLE}
                     WHERE action_taken IS NULL
                    ) AS violations_open,
                    (SELECT COUNT(*) FROM {USER_CONNECTIONS_TABLE}
                     WHERE disconnected_at IS NULL
                    ) AS active_connections,
                    (SELECT COUNT(*) FROM {USERS_TABLE}
                     WHERE expire_at > NOW()
                       AND expire_at < NOW() + INTERVAL '7 days'
                    ) AS expiring_soon,
                    (SELECT COUNT(*) FROM {USERS_TABLE}
                     WHERE traffic_limit_bytes > 0
                       AND used_traffic_bytes >= traffic_limit_bytes
                    ) AS traffic_limit_reached,
                    (SELECT COUNT(*) FROM {USER_HWID_DEVICES_TABLE}) AS hwid_total,
                    (SELECT COUNT(*) FROM torrent_events
                     WHERE detected_at >= NOW() - INTERVAL '24 hours'
                    ) AS torrent_24h
                """
            )

            users_by_status = await conn.fetch(
                select_sql(USERS_TABLE, "UPPER(status) AS status, COUNT(*) AS n",
                    "WHERE status IS NOT NULL GROUP BY UPPER(status)")
            )

            hwid_by_platform = await conn.fetch(
                select_sql(USER_HWID_DEVICES_TABLE,
                    "COALESCE(NULLIF(LOWER(platform), ''), 'unknown') AS platform, COUNT(*) AS n",
                    "GROUP BY 1")
            )

            nodes = await conn.fetch(
                select_sql(NODES_TABLE,
                    "name, cpu_usage, cpu_cores, memory_usage, memory_total_bytes, memory_used_bytes, "
                    "disk_usage, disk_total_bytes, disk_used_bytes, disk_read_speed_bps, disk_write_speed_bps, "
                    "uptime_seconds, traffic_used_bytes, is_connected, is_disabled, "
                    "EXTRACT(EPOCH FROM (NOW() - metrics_updated_at)) AS age_seconds",
                    "WHERE name IS NOT NULL")
            )

            sync_rows = await conn.fetch(
                select_sql(SYNC_METADATA_TABLE,
                    "key, EXTRACT(EPOCH FROM (NOW() - last_sync_at)) AS lag",
                    "WHERE last_sync_at IS NOT NULL")
            )

            violations_by_action = await conn.fetch(
                select_sql(VIOLATIONS_TABLE,
                    "COALESCE(LOWER(recommended_action), 'unknown') AS action, COUNT(*) AS n",
                    "WHERE action_taken IS NULL GROUP BY 1")
            )

            growth = await conn.fetchrow(
                f"""
                SELECT
                    (SELECT COUNT(*) FROM {USERS_TABLE} WHERE created_at >= NOW() - INTERVAL '24 hours') AS created_24h,
                    (SELECT COUNT(*) FROM {USERS_TABLE} WHERE created_at >= NOW() - INTERVAL '7 days')   AS created_7d,
                    (SELECT COUNT(*) FROM {USERS_TABLE} WHERE created_at >= NOW() - INTERVAL '30 days')  AS created_30d,
                    (SELECT COUNT(*) FROM {USERS_TABLE}
                     WHERE expire_at > NOW() AND expire_at < NOW() + INTERVAL '1 day')   AS expiring_1d,
                    (SELECT COUNT(*) FROM {USERS_TABLE}
                     WHERE expire_at > NOW() AND expire_at < NOW() + INTERVAL '30 days') AS expiring_30d,
                    (SELECT COUNT(*) FROM {USERS_TABLE} WHERE used_traffic_bytes < 10737418240) AS traffic_lt_10gb,
                    (SELECT COUNT(*) FROM {USERS_TABLE}
                     WHERE used_traffic_bytes >= 10737418240 AND used_traffic_bytes < 107374182400) AS traffic_10_100gb,
                    (SELECT COUNT(*) FROM {USERS_TABLE}
                     WHERE used_traffic_bytes >= 107374182400 AND used_traffic_bytes < 1099511627776) AS traffic_100gb_1tb,
                    (SELECT COUNT(*) FROM {USERS_TABLE} WHERE used_traffic_bytes >= 1099511627776) AS traffic_gt_1tb
                """
            )

            hwid_limit_reached = await conn.fetchval(
                f"""
                SELECT COUNT(DISTINCT u.uuid)
                FROM {USERS_TABLE} u
                JOIN (
                    SELECT user_uuid, COUNT(*) AS n FROM {USER_HWID_DEVICES_TABLE} GROUP BY user_uuid
                ) d ON d.user_uuid = u.uuid
                WHERE u.hwid_device_limit > 0 AND d.n >= u.hwid_device_limit
                """
            )

            hwid_avg = await conn.fetchval(
                f"SELECT AVG(n)::float FROM ("
                f"  SELECT COUNT(*) AS n FROM {USER_HWID_DEVICES_TABLE} GROUP BY user_uuid"
                f") s"
            )

            # SRH table может отсутствовать на старых инсталляциях — мягко fallback'имся
            sub_req = None
            try:
                sub_req = await conn.fetchrow(
                    f"""
                    SELECT
                        COUNT(*) FILTER (WHERE request_at >= NOW() - INTERVAL '1 hour') AS req_1h,
                        COUNT(*) FILTER (WHERE request_at >= NOW() - INTERVAL '24 hours') AS req_24h
                    FROM {SUBSCRIPTION_REQUEST_HISTORY_TABLE}
                    """
                )
            except Exception:
                sub_req = None

        if row:
            PANEL_ONLINE_USERS.set(int(row["online_users"] or 0))
            PANEL_TOTAL_USERS.set(int(row["total_users"] or 0))
            PANEL_ACTIVE_USERS.set(int(row["active_users"] or 0))
            PANEL_TOTAL_NODES.set(int(row["total_nodes"] or 0))
            PANEL_ONLINE_NODES.set(int(row["online_nodes"] or 0))
            PANEL_VIOLATIONS_OPEN.set(int(row["violations_open"] or 0))
            PANEL_ACTIVE_CONNECTIONS.set(int(row["active_connections"] or 0))
            PANEL_USERS_EXPIRING_SOON.set(int(row["expiring_soon"] or 0))
            PANEL_USERS_TRAFFIC_LIMIT_REACHED.set(int(row["traffic_limit_reached"] or 0))
            PANEL_HWID_DEVICES_TOTAL.set(int(row["hwid_total"] or 0))
            PANEL_TORRENT_EVENTS_24H.set(int(row["torrent_24h"] or 0))

        # Per-label gauges — reset then set to drop stale labels (removed nodes,
        # statuses that fell to 0, etc.)
        PANEL_USERS_BY_STATUS.clear()
        for r in users_by_status:
            status = (r["status"] or "unknown").lower()
            PANEL_USERS_BY_STATUS.labels(status=status).set(int(r["n"]))

        PANEL_HWID_BY_PLATFORM.clear()
        for r in hwid_by_platform:
            PANEL_HWID_BY_PLATFORM.labels(platform=r["platform"]).set(int(r["n"]))

        PANEL_NODE_CPU_USAGE.clear()
        PANEL_NODE_CPU_CORES.clear()
        PANEL_NODE_MEMORY_USAGE.clear()
        PANEL_NODE_MEMORY_TOTAL_BYTES.clear()
        PANEL_NODE_MEMORY_USED_BYTES.clear()
        PANEL_NODE_DISK_USAGE.clear()
        PANEL_NODE_DISK_TOTAL_BYTES.clear()
        PANEL_NODE_DISK_USED_BYTES.clear()
        PANEL_NODE_DISK_READ_BPS.clear()
        PANEL_NODE_DISK_WRITE_BPS.clear()
        PANEL_NODE_LAST_SEEN_SECONDS.clear()
        PANEL_NODE_TRAFFIC_USED_BYTES.clear()
        PANEL_NODE_CONNECTED.clear()
        PANEL_NODE_UPTIME_SECONDS.clear()
        for r in nodes:
            name = r["name"]
            PANEL_NODE_CPU_USAGE.labels(node=name).set(float(r["cpu_usage"] or 0))
            if r["cpu_cores"] is not None:
                PANEL_NODE_CPU_CORES.labels(node=name).set(int(r["cpu_cores"]))
            PANEL_NODE_MEMORY_USAGE.labels(node=name).set(float(r["memory_usage"] or 0))
            PANEL_NODE_MEMORY_TOTAL_BYTES.labels(node=name).set(int(r["memory_total_bytes"] or 0))
            PANEL_NODE_MEMORY_USED_BYTES.labels(node=name).set(int(r["memory_used_bytes"] or 0))
            PANEL_NODE_DISK_USAGE.labels(node=name).set(float(r["disk_usage"] or 0))
            PANEL_NODE_DISK_TOTAL_BYTES.labels(node=name).set(int(r["disk_total_bytes"] or 0))
            PANEL_NODE_DISK_USED_BYTES.labels(node=name).set(int(r["disk_used_bytes"] or 0))
            PANEL_NODE_DISK_READ_BPS.labels(node=name).set(int(r["disk_read_speed_bps"] or 0))
            PANEL_NODE_DISK_WRITE_BPS.labels(node=name).set(int(r["disk_write_speed_bps"] or 0))
            PANEL_NODE_TRAFFIC_USED_BYTES.labels(node=name).set(int(r["traffic_used_bytes"] or 0))
            PANEL_NODE_CONNECTED.labels(node=name).set(
                1 if (r["is_connected"] and not r["is_disabled"]) else 0
            )
            if r["uptime_seconds"] is not None:
                PANEL_NODE_UPTIME_SECONDS.labels(node=name).set(int(r["uptime_seconds"]))
            age = r["age_seconds"]
            if age is not None:
                PANEL_NODE_LAST_SEEN_SECONDS.labels(node=name).set(float(age))

        PANEL_SYNC_LAG_SECONDS.clear()
        for r in sync_rows:
            PANEL_SYNC_LAG_SECONDS.labels(kind=r["key"]).set(float(r["lag"] or 0))

        PANEL_VIOLATIONS_BY_ACTION.clear()
        for r in violations_by_action:
            PANEL_VIOLATIONS_BY_ACTION.labels(action=r["action"]).set(int(r["n"]))

        if growth:
            PANEL_USERS_CREATED.labels(window="24h").set(int(growth["created_24h"] or 0))
            PANEL_USERS_CREATED.labels(window="7d").set(int(growth["created_7d"] or 0))
            PANEL_USERS_CREATED.labels(window="30d").set(int(growth["created_30d"] or 0))
            PANEL_USERS_EXPIRING.labels(window="1d").set(int(growth["expiring_1d"] or 0))
            PANEL_USERS_EXPIRING.labels(window="7d").set(int(row["expiring_soon"] or 0))
            PANEL_USERS_EXPIRING.labels(window="30d").set(int(growth["expiring_30d"] or 0))
            PANEL_USERS_BY_TRAFFIC_BUCKET.labels(bucket="lt_10gb").set(int(growth["traffic_lt_10gb"] or 0))
            PANEL_USERS_BY_TRAFFIC_BUCKET.labels(bucket="10_100gb").set(int(growth["traffic_10_100gb"] or 0))
            PANEL_USERS_BY_TRAFFIC_BUCKET.labels(bucket="100gb_1tb").set(int(growth["traffic_100gb_1tb"] or 0))
            PANEL_USERS_BY_TRAFFIC_BUCKET.labels(bucket="gt_1tb").set(int(growth["traffic_gt_1tb"] or 0))

        PANEL_USERS_HWID_LIMIT_REACHED.set(int(hwid_limit_reached or 0))
        PANEL_HWID_DEVICES_PER_USER_AVG.set(float(hwid_avg or 0))

        if sub_req:
            PANEL_SUBSCRIPTION_REQUESTS.labels(window="1h").set(int(sub_req["req_1h"] or 0))
            PANEL_SUBSCRIPTION_REQUESTS.labels(window="24h").set(int(sub_req["req_24h"] or 0))

        # asyncpg pool stats
        pool = getattr(db_service, "_pool", None) or getattr(db_service, "pool", None)
        if pool is not None:
            try:
                size = pool.get_size()
                idle = pool.get_idle_size()
                PANEL_DB_POOL_SIZE.set(int(size))
                PANEL_DB_POOL_USED.set(int(max(0, size - idle)))
            except Exception:
                pass


gauge_updater = GaugeUpdater()
