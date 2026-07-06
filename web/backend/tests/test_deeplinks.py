"""Тесты shared/deeplinks.py — порт @incy/link-encoder + открытые URL-схемы.

Эталонный вектор взят из test/index.test.ts пакета @incy/link-encoder —
он же используется в интероп-тестах iOS/Android/Desktop клиентов INCY,
так что совпадение гарантирует wire-совместимость порта.
"""
import pytest

from shared.deeplinks import (
    IncyLinkError,
    build_deeplinks,
    decrypt_incy_link,
    encrypt_incy_link,
)

REFERENCE_IV = bytes.fromhex("000102030405060708090a0b")
REFERENCE_URL = "https://sub.example.com/test-vector"
REFERENCE_LINK = (
    "incy://crypt1/AAECAwQFBgcICQoLNyIQL3rDwRZqnyoD8pGKSLXP6o8NdSXQVSSALNbbUyIr"
    "__tWGFUexdIfKvvmDnuDGbmBvuppfNef6aKNZUwOm4c-Sg"
)


def test_reference_vector_matches_incy_clients():
    assert encrypt_incy_link(REFERENCE_URL, _iv=REFERENCE_IV) == REFERENCE_LINK


def test_roundtrip_without_name():
    url = "https://sub.example.com/test-token"
    link = encrypt_incy_link(url)
    assert link.startswith("incy://crypt1/")
    decoded = decrypt_incy_link(link)
    assert decoded == {"url": url, "name": None}


def test_roundtrip_preserves_unicode_name():
    url = "https://sub.example.com/abc"
    name = "Мой VPN — тест"
    decoded = decrypt_incy_link(encrypt_incy_link(url, name))
    assert decoded == {"url": url, "name": name}


def test_random_iv_gives_unique_links():
    url = "https://test.example/abc"
    a = encrypt_incy_link(url)
    b = encrypt_incy_link(url)
    assert a != b
    assert decrypt_incy_link(a)["url"] == url
    assert decrypt_incy_link(b)["url"] == url


def test_name_truncated_to_128_chars():
    link = encrypt_incy_link("https://test/x", "X" * 500)
    assert len(decrypt_incy_link(link)["name"]) == 128


def test_tampered_payload_rejected():
    link = encrypt_incy_link("https://test.example/x")
    ch = "B" if link[-10] == "A" else "A"
    tampered = link[:-10] + ch + link[-9:]
    with pytest.raises(IncyLinkError):
        decrypt_incy_link(tampered)


def test_decrypt_rejects_foreign_links():
    for bad in ("https://incy.cc/foo", "incy://add/https%3A%2F%2Ffoo.bar", ""):
        with pytest.raises(IncyLinkError):
            decrypt_incy_link(bad)


def test_encrypt_rejects_empty_url():
    with pytest.raises(IncyLinkError):
        encrypt_incy_link("")


def test_encrypt_rejects_wrong_iv_length():
    with pytest.raises(IncyLinkError):
        encrypt_incy_link("https://test/x", _iv=b"\x00" * 11)


def test_build_deeplinks_structure():
    url = "https://sub.example.com/abc"
    links = build_deeplinks(url, "Test Panel")
    by_id = {l["id"]: l["link"] for l in links}
    assert by_id["happ"] == f"happ://add/{url}"
    assert by_id["streisand"] == f"streisand://import/{url}"
    assert by_id["hiddify"] == f"hiddify://import/{url}"
    assert by_id["clash"] == f"clash://install-config?url={url}"
    assert by_id["v2rayng"] == f"v2rayng://install-config?name=Test%20Panel&url={url}"
    assert decrypt_incy_link(by_id["incy"]) == {"url": url, "name": "Test Panel"}
    assert all(l["label"] for l in links)


def test_build_deeplinks_empty_url():
    assert build_deeplinks("") == []
