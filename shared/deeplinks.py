"""Deep-links импорта подписки в клиентские приложения.

Открытые URL-схемы (Happ, v2rayNG, Streisand, Hiddify, Clash) — по канону
remnawave/subscription-page (app-config.json): схема + subscription URL
простой конкатенацией.

INCY — шифрованный формат `incy://crypt1/<payload>`, порт открытого пакета
@incy/link-encoder (MIT, INCY LLC). Это ОБФУСКАЦИЯ, а не криптография:
AES-256-GCM с глобальным ключом, который зашит в каждый клиент INCY и
восстановим из открытого пакета. Прячет subscription-домен от автосканеров
в чатах — не от целевого реверса. Wire-формат: iv(12) + ciphertext + tag(16)
в base64url без паддинга; plaintext — компактный JSON с сортированными
ключами (побайтово совместим с iOS/Android/Desktop клиентами INCY).
"""
import base64
import hashlib
import json
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

# Соль и раскладка keymat — из @incy/link-encoder (см. докстринг модуля).
_INCY_SALT = b"incy" + b"deep" + b"crypt1" + b"v2026.06"
_INCY_KEYMAT_A_OFFSET = 1024
_INCY_KEYMAT_B_OFFSET = 2048
_INCY_KEYMAT_LEN = 32

# Отпечаток ключа K1, общий для всех платформ INCY. Если derive даёт другой —
# keymat-блобы рассинхронизированы с клиентами, ссылки не декодируются.
_INCY_KEY_FINGERPRINT = "b6bf708471cc90043232967660aade86a50b4e57929db2e53c5fa34db624c08c"

_INCY_PREFIX = "incy://crypt1/"
_INCY_NAME_MAX = 128

_incy_key_cache: Optional[bytes] = None


class IncyLinkError(ValueError):
    """Некорректная ссылка incy://crypt1 или рассинхрон keymat."""


def _derive_incy_key() -> bytes:
    global _incy_key_cache
    if _incy_key_cache is not None:
        return _incy_key_cache
    with open(os.path.join(_ASSETS_DIR, "incy_keymat_a.bin"), "rb") as f:
        a = f.read()
    with open(os.path.join(_ASSETS_DIR, "incy_keymat_b.bin"), "rb") as f:
        b = f.read()
    km_a = a[_INCY_KEYMAT_A_OFFSET:_INCY_KEYMAT_A_OFFSET + _INCY_KEYMAT_LEN]
    km_b = b[_INCY_KEYMAT_B_OFFSET:_INCY_KEYMAT_B_OFFSET + _INCY_KEYMAT_LEN]
    if len(km_a) < _INCY_KEYMAT_LEN or len(km_b) < _INCY_KEYMAT_LEN:
        raise IncyLinkError("incy keymat assets are smaller than expected")
    key = hashlib.sha256(_INCY_SALT + km_a + km_b).digest()
    fingerprint = hashlib.sha256(key).hexdigest()
    if fingerprint != _INCY_KEY_FINGERPRINT:
        raise IncyLinkError(
            f"incy K1 fingerprint mismatch: expected {_INCY_KEY_FINGERPRINT}, got {fingerprint}"
        )
    _incy_key_cache = key
    return key


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _sorted_compact_json(payload: dict) -> bytes:
    # Байт-в-байт как sortedCompactJson в @incy/link-encoder
    # (JSON.stringify не эскейпит не-ASCII → ensure_ascii=False).
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def encrypt_incy_link(url: str, name: Optional[str] = None, *, _iv: Optional[bytes] = None) -> str:
    """Собирает ссылку incy://crypt1/<payload> из subscription URL.

    _iv — только для тестовых векторов; в проде IV всегда случайный.
    """
    if not url or not isinstance(url, str):
        raise IncyLinkError("url must be a non-empty string")
    key = _derive_incy_key()
    payload: dict = {"url": url, "v": 1}
    if name:
        payload["n"] = name[:_INCY_NAME_MAX]
    plaintext = _sorted_compact_json(payload)

    iv = _iv if _iv is not None else os.urandom(12)
    if len(iv) != 12:
        raise IncyLinkError("iv must be 12 bytes")
    # AESGCM.encrypt возвращает ciphertext+tag — ровно wire-хвост формата.
    wire = iv + AESGCM(key).encrypt(iv, plaintext, None)
    return _INCY_PREFIX + _b64url_encode(wire)


def decrypt_incy_link(link: str) -> dict:
    """Обратная операция — для тестов и самопроверки (декодируют клиенты)."""
    if not link or not link.startswith(_INCY_PREFIX):
        raise IncyLinkError("not an incy://crypt1 link")
    wire = _b64url_decode(link[len(_INCY_PREFIX):])
    if len(wire) < 12 + 16:
        raise IncyLinkError("payload too short")
    key = _derive_incy_key()
    try:
        plaintext = AESGCM(key).decrypt(wire[:12], wire[12:], None)
    except Exception as exc:
        raise IncyLinkError(f"decryption failed: {exc}") from exc
    payload = json.loads(plaintext.decode("utf-8"))
    return {"url": payload.get("url"), "name": payload.get("n")}


def build_deeplinks(subscription_url: str, name: Optional[str] = None) -> list[dict]:
    """Ссылки быстрого импорта подписки для популярных клиентов.

    Возвращает [{id, label, link}]; INCY — шифрованная, остальные — открытые
    URL-схемы поверх subscription URL (как на сабстранице Remnawave).
    """
    if not subscription_url:
        return []
    from urllib.parse import quote

    encoded_name = quote(name or "", safe="")
    links = [
        {"id": "happ", "label": "Happ", "link": f"happ://add/{subscription_url}"},
        {
            "id": "v2rayng",
            "label": "v2rayNG",
            "link": f"v2rayng://install-config?name={encoded_name}&url={subscription_url}",
        },
        {"id": "streisand", "label": "Streisand", "link": f"streisand://import/{subscription_url}"},
        {"id": "hiddify", "label": "Hiddify", "link": f"hiddify://import/{subscription_url}"},
        {"id": "clash", "label": "Clash", "link": f"clash://install-config?url={subscription_url}"},
        {"id": "incy", "label": "INCY", "link": encrypt_incy_link(subscription_url, name)},
    ]
    return links
