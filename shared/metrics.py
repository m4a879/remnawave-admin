"""Shared Prometheus counters used by both web-backend and bot.

Lives in `shared/` so any subsystem can `.inc()` a counter without creating
a circular import with `web/backend/`. The web-backend `core/metrics.py`
re-exports these alongside its HTTP middleware and gauge updater so the
public surface stays unchanged for existing code.

Adding new counters: define them here, import them where the event happens,
and call `.inc()` (or `.labels(...).inc()`). Histograms and gauges that
need DB access still live in `web/backend/core/metrics.py`.
"""
from __future__ import annotations

from prometheus_client import Counter

# ── Collector ────────────────────────────────────────────────────

COLLECTOR_BATCHES_RECEIVED = Counter(
    "panel_collector_batches_received_total",
    "Total node-agent batches accepted by /collector/batch.",
)

COLLECTOR_BATCHES_REJECTED = Counter(
    "panel_collector_batches_rejected_total",
    "Total node-agent batches rejected.",
    ["reason"],  # rate_limit, auth, malformed, mismatch
)

COLLECTOR_CONNECTIONS_PROCESSED = Counter(
    "panel_collector_connections_processed_total",
    "Connection records ingested from accepted batches.",
)

# ── Violations ───────────────────────────────────────────────────

VIOLATIONS_DETECTED = Counter(
    "panel_violations_detected_total",
    "Violations stored to DB by the detection pipeline.",
    ["action"],  # no_action, monitor, warn, soft_block, temp_block, hard_block
)

# ── Notifications ────────────────────────────────────────────────

NOTIFICATIONS_SENT = Counter(
    "panel_notifications_sent_total",
    "Notifications successfully delivered.",
    ["channel"],  # in_app, telegram, email, webhook, push
)

NOTIFICATIONS_FAILED = Counter(
    "panel_notifications_failed_total",
    "Notification delivery attempts that returned an error.",
    ["channel"],
)

# ── Sync ─────────────────────────────────────────────────────────

SYNC_RUNS = Counter(
    "panel_sync_runs_total",
    "Panel→DB sync runs completed.",
    ["kind", "result"],  # kind=users|nodes|hosts, result=ok|error
)
