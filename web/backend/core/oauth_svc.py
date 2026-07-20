"""OAuth2 SSO (Google / GitHub) — authorize-URL, обмен кода, userinfo, привязки.

Модель безопасности: авто-создания аккаунтов НЕТ. Вход по OAuth работает только
если (provider, external_id) привязан к существующему admin-аккаунту. Привязка
делается залогиненным админом (self-service). Секреты провайдеров зашифрованы.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from jose import jwt, JWTError

from web.backend.core.crypto import encrypt_field, decrypt_field
from shared.db_schema import OAUTH_LINKS_TABLE as TBL

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0

_PROVIDERS: Dict[str, Dict[str, str]] = {
    "google": {
        "name": "Google",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile",
    },
    "github": {
        "name": "GitHub",
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "scope": "read:user user:email",
    },
}


class OAuthError(Exception):
    """Ошибка OAuth с человекочитаемым сообщением."""


def providers() -> List[Dict[str, Any]]:
    return [{"slug": s, "name": p["name"], "configured": is_configured(s)} for s, p in _PROVIDERS.items()]


def is_provider(slug: str) -> bool:
    return slug in _PROVIDERS


# ── Креды провайдеров ────────────────────────────────────────────

def _cid_key(p: str) -> str:
    return f"oauth_{p}_client_id"


def _secret_key(p: str) -> str:
    return f"oauth_{p}_client_secret"


def get_client_id(p: str) -> str:
    from shared.config_service import config_service
    return str(config_service.get(_cid_key(p), "") or "").strip()


def get_client_secret(p: str) -> str:
    from shared.config_service import config_service
    enc = config_service.get(_secret_key(p), None)
    if not enc:
        return ""
    try:
        return decrypt_field(str(enc))
    except Exception:  # noqa: BLE001
        logger.warning("oauth: secret %s не расшифровался", p)
        return ""


def is_configured(p: str) -> bool:
    return bool(get_client_id(p) and get_client_secret(p))


async def save_creds(p: str, client_id: str, client_secret: str) -> None:
    await _write(_cid_key(p), client_id.strip())
    await _write(_secret_key(p), encrypt_field(client_secret.strip()) if client_secret.strip() else "")


async def clear_creds(p: str) -> None:
    await _write(_cid_key(p), "")
    await _write(_secret_key(p), "")


async def _write(key: str, value: str) -> None:
    from shared.database import db_service
    from shared.db_query import update_sql
    from shared.db_schema import BOT_CONFIG_TABLE
    from shared.config_service import config_service
    if not db_service.is_connected:
        raise OAuthError("База данных недоступна")
    async with db_service.acquire() as conn:
        await conn.execute(
            update_sql(BOT_CONFIG_TABLE, "value = $2, updated_at = NOW()", "key = $1"), key, value)
    try:
        if key in config_service._cache:
            config_service._cache[key].value = value
    except Exception:  # noqa: BLE001
        pass


# ── redirect_uri / state ─────────────────────────────────────────

def _origin(request) -> str:
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    proto = (request.headers.get("x-forwarded-proto") or (request.url.scheme if request.url else "https")).split(",")[0].strip()
    if not host:
        raise OAuthError("не удалось определить origin")
    return f"{proto}://{host}"


def _redirect_uri(request) -> str:
    from shared.config_service import config_service
    override = str(config_service.get("oauth_redirect_uri", "") or "").strip()
    return override or f"{_origin(request)}/oauth/callback"


def _make_state(provider: str, mode: str, account_id: Optional[int]) -> str:
    from web.backend.core.config import get_web_settings
    settings = get_web_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "type": "oauth_state", "provider": provider, "mode": mode,
        "nonce": secrets.token_urlsafe(8),
        "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    if account_id is not None:
        payload["aid"] = account_id
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _read_state(state: str) -> Dict[str, Any]:
    from web.backend.core.config import get_web_settings
    settings = get_web_settings()
    try:
        p = jwt.decode(state, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise OAuthError("state истёк или недействителен")
    if p.get("type") != "oauth_state":
        raise OAuthError("неверный state")
    return p


# ── Authorize / callback ─────────────────────────────────────────

def build_authorize_url(request, provider: str, mode: str, account_id: Optional[int]) -> str:
    if provider not in _PROVIDERS:
        raise OAuthError("неизвестный провайдер")
    if not is_configured(provider):
        raise OAuthError("Провайдер не настроен (нет client_id/secret)")
    prov = _PROVIDERS[provider]
    params = {
        "client_id": get_client_id(provider),
        "redirect_uri": _redirect_uri(request),
        "response_type": "code",
        "scope": prov["scope"],
        "state": _make_state(provider, mode, account_id),
    }
    if provider == "google":
        params["access_type"] = "online"
        params["prompt"] = "select_account"
    return f"{prov['authorize']}?{urlencode(params)}"


async def _exchange_code(provider: str, code: str, redirect_uri: str) -> str:
    prov = _PROVIDERS[provider]
    data = {
        "client_id": get_client_id(provider),
        "client_secret": get_client_secret(provider),
        "code": code, "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(prov["token"], data=data, headers={"Accept": "application/json"})
    except httpx.HTTPError as e:
        raise OAuthError(f"сеть: {e}")
    try:
        j = r.json()
    except ValueError:
        raise OAuthError(f"токен-эндпоинт вернул не JSON (HTTP {r.status_code})")
    tok = j.get("access_token")
    if not tok:
        raise OAuthError(str(j.get("error_description") or j.get("error") or "не выдан access_token"))
    return tok


async def _userinfo(provider: str, access_token: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        if provider == "google":
            r = await c.get("https://openidconnect.googleapis.com/v1/userinfo", headers=headers)
            d = r.json() if r.status_code == 200 else {}
            eid = d.get("sub")
            if not eid:
                raise OAuthError("Google не вернул идентификатор")
            return {"external_id": str(eid), "email": d.get("email"), "name": d.get("name") or d.get("email")}
        # github
        r = await c.get("https://api.github.com/user", headers=headers)
        d = r.json() if r.status_code == 200 else {}
        eid = d.get("id")
        if not eid:
            raise OAuthError("GitHub не вернул идентификатор")
        email = d.get("email")
        if not email:
            try:
                er = await c.get("https://api.github.com/user/emails", headers=headers)
                emails = er.json() if er.status_code == 200 else []
                primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
                email = (primary or (emails[0] if emails else {})).get("email")
            except Exception:  # noqa: BLE001
                email = None
        return {"external_id": str(eid), "email": email, "name": d.get("name") or d.get("login")}


async def exchange(request, code: str, state: str) -> Dict[str, Any]:
    """Обменять code → userinfo. Провайдер берётся из подписанного state."""
    st = _read_state(state)
    provider = st.get("provider")
    if provider not in _PROVIDERS:
        raise OAuthError("неизвестный провайдер в state")
    token = await _exchange_code(provider, code, _redirect_uri(request))
    return {"state": st, "provider": provider, "userinfo": await _userinfo(provider, token)}


# ── БД привязок ──────────────────────────────────────────────────

def _row(r) -> Dict[str, Any]:
    d = dict(r)
    for k in ("created_at", "last_used_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


async def get_link(provider: str, external_id: str) -> Optional[Dict[str, Any]]:
    from shared.database import db_service
    if not db_service.is_connected:
        return None
    async with db_service.acquire() as conn:
        r = await conn.fetchrow(
            f"SELECT * FROM {TBL} WHERE provider = $1 AND external_id = $2", provider, external_id)
    return _row(r) if r else None


async def list_links(account_id: int) -> List[Dict[str, Any]]:
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(f"SELECT * FROM {TBL} WHERE account_id = $1 ORDER BY created_at", account_id)
    return [_row(r) for r in rows]


async def save_link(account_id: int, provider: str, external_id: str,
                    email: Optional[str], name: Optional[str]) -> None:
    from shared.database import db_service
    if not db_service.is_connected:
        raise OAuthError("База данных недоступна")
    existing = await get_link(provider, external_id)
    if existing and int(existing["account_id"]) != int(account_id):
        raise OAuthError("Этот аккаунт уже привязан к другому админу")
    async with db_service.acquire() as conn:
        await conn.execute(
            f"""INSERT INTO {TBL} (account_id, provider, external_id, email, name)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (provider, external_id)
                DO UPDATE SET email = EXCLUDED.email, name = EXCLUDED.name""",
            account_id, provider, external_id, email, name)


async def touch_link(provider: str, external_id: str) -> None:
    from shared.database import db_service
    if not db_service.is_connected:
        return
    async with db_service.acquire() as conn:
        await conn.execute(
            f"UPDATE {TBL} SET last_used_at = NOW() WHERE provider = $1 AND external_id = $2",
            provider, external_id)


async def delete_link(link_id: int, account_id: int) -> bool:
    from shared.database import db_service
    if not db_service.is_connected:
        return False
    async with db_service.acquire() as conn:
        res = await conn.execute(f"DELETE FROM {TBL} WHERE id = $1 AND account_id = $2", link_id, account_id)
    return isinstance(res, str) and res.endswith("1")
