"""Mail server API endpoints."""
import json
import logging
from email.header import decode_header as _decode_mime_header
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from shared.db_schema import DOMAIN_CONFIG_TABLE, EMAIL_QUEUE_TABLE, EMAIL_INBOX_TABLE, SMTP_CREDENTIALS_TABLE
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql

from web.backend.core.errors import api_error, E


def _decode_subject(raw: str | None) -> str:
    """Decode MIME-encoded subject like =?utf-8?b?...?= to readable text."""
    if not raw or '=?' not in raw:
        return raw or ''
    try:
        parts = _decode_mime_header(raw)
        decoded = []
        for data, charset in parts:
            if isinstance(data, bytes):
                decoded.append(data.decode(charset or 'utf-8', errors='replace'))
            else:
                decoded.append(data)
        return ' '.join(decoded)
    except Exception:
        return raw
from web.backend.api.deps import AdminUser, get_client_ip, require_permission
from web.backend.core.audit import write_audit_log
from web.backend.schemas.mailserver import (
    ComposeEmail,
    DnsCheckResult,
    DnsRecordItem,
    DomainCreate,
    DomainRead,
    DomainUpdate,
    EmailQueueDetail,
    EmailQueueItem,
    InboxDetail,
    InboxItem,
    InboxMarkRead,
    QueueStats,
    SmtpCredentialCreate,
    SmtpCredentialRead,
    SmtpCredentialUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mailserver", tags=["mailserver"])


# ── Domain endpoints ──────────────────────────────────────────────

@router.post("/domains", response_model=DomainRead)
async def create_domain(
    payload: DomainCreate,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Create a new mail domain with auto-generated DKIM keys."""
    from web.backend.core.mail.mail_service import mail_service

    try:
        row = await mail_service.setup_domain(payload.domain)
        # Apply extra settings
        from shared.database import db_service
        async with db_service.acquire() as conn:
            await conn.execute(
                update_sql(DOMAIN_CONFIG_TABLE, "inbound_enabled = $1, outbound_enabled = $2, max_send_per_hour = $3, from_name = $4", "id = $5"),
                payload.inbound_enabled, payload.outbound_enabled,
                payload.max_send_per_hour, payload.from_name, row["id"],
            )
            updated = await conn.fetchrow(select_sql(DOMAIN_CONFIG_TABLE, "*", "WHERE id = $1"), row["id"])
        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="mailserver.create_domain", resource="mailserver",
            resource_id=str(row["id"]),
            details=json.dumps({"domain": payload.domain}),
            ip_address=get_client_ip(request),
        )
        return dict(updated)
    except Exception as e:
        logger.error("Domain creation failed: %s", e)
        raise HTTPException(status_code=400, detail="Internal server error")


@router.get("/domains", response_model=List[DomainRead])
async def list_domains(
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """List all configured mail domains."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(select_sql(DOMAIN_CONFIG_TABLE, "*", "ORDER BY id"))
    return [dict(r) for r in rows]


@router.get("/domains/{domain_id}", response_model=DomainRead)
async def get_domain(
    domain_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get domain details."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(select_sql(DOMAIN_CONFIG_TABLE, "*", "WHERE id = $1"), domain_id)
    if not row:
        raise api_error(404, E.DOMAIN_NOT_FOUND)
    return dict(row)


@router.put("/domains/{domain_id}", response_model=DomainRead)
async def update_domain(
    domain_id: int,
    payload: DomainUpdate,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Update domain settings."""
    from shared.database import db_service

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    set_clauses = []
    values = []
    idx = 1
    for key, val in updates.items():
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_clauses.append(f"updated_at = NOW()")
    values.append(domain_id)

    query = update_sql(DOMAIN_CONFIG_TABLE, ', '.join(set_clauses), f"id = ${idx}", returning="*")
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(query, *values)
    if not row:
        raise api_error(404, E.DOMAIN_NOT_FOUND)
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.update_domain", resource="mailserver",
        resource_id=str(domain_id),
        details=json.dumps({"updated_fields": list(updates.keys())}),
        ip_address=get_client_ip(request),
    )
    return dict(row)


@router.delete("/domains/{domain_id}")
async def delete_domain(
    domain_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "delete")),
):
    """Delete a domain and its DKIM keys."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        deleted = await conn.execute(delete_sql(DOMAIN_CONFIG_TABLE, "id = $1"), domain_id)
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.delete_domain", resource="mailserver",
        resource_id=str(domain_id),
        details=json.dumps({"domain_id": domain_id}),
        ip_address=get_client_ip(request),
    )
    return {"ok": True}


@router.post("/domains/{domain_id}/check-dns", response_model=DnsCheckResult)
async def check_domain_dns(
    domain_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Run DNS verification for a domain."""
    from web.backend.core.mail.mail_service import mail_service
    result = await mail_service.check_domain_dns(domain_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/domains/{domain_id}/dns-records", response_model=List[DnsRecordItem])
async def get_domain_dns_records(
    domain_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get required DNS records for a domain."""
    from web.backend.core.mail.mail_service import mail_service
    records = await mail_service.get_domain_dns_records(domain_id)
    if not records:
        raise api_error(404, E.DOMAIN_NOT_FOUND)
    return records


# ── Queue endpoints ───────────────────────────────────────────────

@router.get("/queue", response_model=List[EmailQueueItem])
async def list_queue(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """List outbound email queue."""
    from shared.database import db_service

    conditions = []
    params = []
    idx = 1

    if status_filter:
        conditions.append(f"status = ${idx}")
        params.append(status_filter)
        idx += 1
    if category:
        conditions.append(f"category = ${idx}")
        params.append(category)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    query = select_sql(EMAIL_QUEUE_TABLE,
        "id, from_email, to_email, subject, status, category, priority, attempts, max_attempts, last_error, message_id, created_at, sent_at",
        f"{where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}")

    async with db_service.acquire() as conn:
        rows = await conn.fetch(query, *params)
    result = []
    for r in rows:
        d = dict(r)
        d["subject"] = _decode_subject(d.get("subject"))
        result.append(d)
    return result


@router.get("/queue/stats", response_model=QueueStats)
async def get_queue_stats(
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get queue statistics."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            select_sql(EMAIL_QUEUE_TABLE,
                "COUNT(*) FILTER (WHERE status = 'pending') AS pending, "
                "COUNT(*) FILTER (WHERE status = 'sending') AS sending, "
                "COUNT(*) FILTER (WHERE status = 'sent') AS sent, "
                "COUNT(*) FILTER (WHERE status = 'failed' AND attempts >= max_attempts) AS failed, "
                "COUNT(*) AS total")
        )
    return dict(row)


@router.get("/queue/{item_id}", response_model=EmailQueueDetail)
async def get_queue_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get queue item details."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(select_sql(EMAIL_QUEUE_TABLE, "*", "WHERE id = $1"), item_id)
    if not row:
        raise api_error(404, E.QUEUE_ITEM_NOT_FOUND)
    d = dict(row)
    d["subject"] = _decode_subject(d.get("subject"))
    return d


@router.post("/queue/{item_id}/retry")
async def retry_queue_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Retry a failed queue item."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        result = await conn.execute(
            update_sql(EMAIL_QUEUE_TABLE, "status = 'pending', attempts = 0, next_attempt_at = NOW(), last_error = NULL", "id = $1 AND status = 'failed'"),
            item_id,
        )
    return {"ok": True}


@router.post("/queue/{item_id}/cancel")
async def cancel_queue_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Cancel a pending queue item."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        await conn.execute(
            update_sql(EMAIL_QUEUE_TABLE, "status = 'cancelled'", "id = $1 AND status IN ('pending', 'failed')"),
            item_id,
        )
    return {"ok": True}


@router.delete("/queue")
async def clear_old_queue(
    days: int = Query(30, ge=1, le=365),
    admin: AdminUser = Depends(require_permission("mailserver", "delete")),
):
    """Clear queue items older than N days."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        result = await conn.execute(
            delete_sql(EMAIL_QUEUE_TABLE, "created_at < NOW() - ($1 || ' days')::INTERVAL"),
            str(days),
        )
    return {"ok": True, "deleted": result}


# ── Inbox endpoints ───────────────────────────────────────────────

@router.get("/inbox", response_model=List[InboxItem])
async def list_inbox(
    is_read: Optional[bool] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """List inbox messages."""
    from shared.database import db_service

    conditions = []
    params = []
    idx = 1

    if is_read is not None:
        conditions.append(f"is_read = ${idx}")
        params.append(is_read)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    query = select_sql(EMAIL_INBOX_TABLE,
        "id, mail_from, rcpt_to, from_header, subject, date_header, is_read, is_spam, has_attachments, attachment_count, created_at",
        f"{where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}")

    async with db_service.acquire() as conn:
        rows = await conn.fetch(query, *params)
    result = []
    for r in rows:
        d = dict(r)
        d["subject"] = _decode_subject(d.get("subject"))
        result.append(d)
    return result


@router.get("/inbox/{item_id}", response_model=InboxDetail)
async def get_inbox_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get full inbox message."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(select_sql(EMAIL_INBOX_TABLE, "*", "WHERE id = $1"), item_id)
    if not row:
        raise api_error(404, E.MESSAGE_NOT_FOUND)
    d = dict(row)
    d["subject"] = _decode_subject(d.get("subject"))
    return d


@router.post("/inbox/mark-read")
async def mark_inbox_read(
    payload: InboxMarkRead,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Mark inbox messages as read."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        if payload.ids:
            await conn.execute(
                update_sql(EMAIL_INBOX_TABLE, "is_read = true", "id = ANY($1::bigint[])"),
                payload.ids,
            )
        else:
            await conn.execute(update_sql(EMAIL_INBOX_TABLE, "is_read = true", "is_read = false"))
    return {"ok": True}


@router.delete("/inbox/{item_id}")
async def delete_inbox_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "delete")),
):
    """Delete an inbox message."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        await conn.execute(delete_sql(EMAIL_INBOX_TABLE, "id = $1"), item_id)
    return {"ok": True}


# ── Compose / Send ────────────────────────────────────────────────

@router.post("/send")
async def send_email(
    payload: ComposeEmail,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Send an email via the built-in mail server."""
    from web.backend.core.mail.mail_service import mail_service

    queue_id = await mail_service.send_email(
        to_email=payload.to_email,
        subject=payload.subject,
        body_text=payload.body_text,
        body_html=payload.body_html,
        from_email=payload.from_email,
        from_name=payload.from_name,
        category="manual",
        priority=1,
    )
    if queue_id is None:
        raise api_error(400, E.NO_OUTBOUND_DOMAIN)
    return {"ok": True, "queue_id": queue_id}


@router.post("/send/test")
async def send_test_email(
    payload: ComposeEmail,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Send a test email to verify mail server setup."""
    from web.backend.core.mail.mail_service import mail_service
    from web.backend.core.notification_service import _build_html_email

    subject = payload.subject or "Mail Server Test"
    body_text = payload.body_text or "This is a test email from your mail server. If you received this, your setup is working correctly!"
    body_html = payload.body_html or _build_html_email(
        title=subject,
        body=body_text,
        severity="success",
    )

    queue_id = await mail_service.send_email(
        to_email=payload.to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        from_email=payload.from_email,
        from_name=payload.from_name,
        category="test",
        priority=2,
    )
    if queue_id is None:
        raise api_error(400, E.NO_OUTBOUND_DOMAIN)
    return {"ok": True, "queue_id": queue_id}


# ── SMTP Credentials endpoints ────────────────────────────────────

@router.post("/smtp-credentials", response_model=SmtpCredentialRead)
async def create_smtp_credential(
    payload: SmtpCredentialCreate,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Create SMTP credentials for external services to relay mail."""
    from web.backend.core.mail.submission_server import hash_password_for_storage
    from shared.database import db_service

    password_hash = hash_password_for_storage(payload.password)
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                insert_sql(SMTP_CREDENTIALS_TABLE,
                    ["username", "password_hash", "description", "allowed_from_domains", "max_send_per_hour"],
                    returning="*"),
                payload.username, password_hash, payload.description,
                payload.allowed_from_domains, payload.max_send_per_hour,
            )
        from web.backend.core.mail.mail_service import mail_service
        await mail_service.refresh_smtp_credentials()
        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="mailserver.create_smtp_credential", resource="mailserver",
            resource_id=str(row["id"]),
            details=json.dumps({"username": payload.username}),
            ip_address=get_client_ip(request),
        )
        return dict(row)
    except Exception as e:
        logger.error("SMTP credential creation failed: %s", e)
        raise HTTPException(status_code=400, detail="Internal server error")


@router.get("/smtp-credentials", response_model=List[SmtpCredentialRead])
async def list_smtp_credentials(
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """List all SMTP credentials."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            select_sql(SMTP_CREDENTIALS_TABLE,
                "id, username, description, is_active, allowed_from_domains, max_send_per_hour, last_login_at, last_login_ip, created_at, updated_at",
                "ORDER BY id")
        )
    return [dict(r) for r in rows]


@router.get("/smtp-credentials/{cred_id}", response_model=SmtpCredentialRead)
async def get_smtp_credential(
    cred_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get SMTP credential details."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            select_sql(SMTP_CREDENTIALS_TABLE,
                "id, username, description, is_active, allowed_from_domains, max_send_per_hour, last_login_at, last_login_ip, created_at, updated_at",
                "WHERE id = $1"), cred_id,
        )
    if not row:
        raise api_error(404, E.SMTP_CREDENTIAL_NOT_FOUND)
    return dict(row)


@router.put("/smtp-credentials/{cred_id}", response_model=SmtpCredentialRead)
async def update_smtp_credential(
    cred_id: int,
    payload: SmtpCredentialUpdate,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Update SMTP credential settings."""
    from shared.database import db_service

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    # Hash password if provided
    if "password" in updates:
        from web.backend.core.mail.submission_server import hash_password_for_storage
        updates["password_hash"] = hash_password_for_storage(updates.pop("password"))

    set_clauses = []
    values = []
    idx = 1
    for key, val in updates.items():
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_clauses.append("updated_at = NOW()")
    values.append(cred_id)

    query = update_sql(SMTP_CREDENTIALS_TABLE, ', '.join(set_clauses), f"id = ${idx}", returning="id, username, description, is_active, allowed_from_domains, max_send_per_hour, last_login_at, last_login_ip, created_at, updated_at")
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(query, *values)
    if not row:
        raise api_error(404, E.SMTP_CREDENTIAL_NOT_FOUND)
    from web.backend.core.mail.mail_service import mail_service
    await mail_service.refresh_smtp_credentials()
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.update_smtp_credential", resource="mailserver",
        resource_id=str(cred_id),
        details=json.dumps({"updated_fields": list(updates.keys())}),
        ip_address=get_client_ip(request),
    )
    return dict(row)


@router.delete("/smtp-credentials/{cred_id}")
async def delete_smtp_credential(
    cred_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "delete")),
):
    """Delete an SMTP credential."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        await conn.execute(delete_sql(SMTP_CREDENTIALS_TABLE, "id = $1"), cred_id)
    from web.backend.core.mail.mail_service import mail_service
    await mail_service.refresh_smtp_credentials()
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.delete_smtp_credential", resource="mailserver",
        resource_id=str(cred_id),
        details=json.dumps({"credential_id": cred_id}),
        ip_address=get_client_ip(request),
    )
    return {"ok": True}
