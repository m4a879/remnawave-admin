"""SSRF-фильтр вебхуков: check_url_safety / _ip_is_blocked.

Проверяем усиленный блок-лист (IPv4-mapped IPv6, 0.0.0.0/8, CGNAT, private/
reserved/link-local) и что публичные адреса проходят. URL используют
литеральные IP — без обращения к DNS.
"""
import ipaddress

import pytest

from web.backend.core.webhook_security import check_url_safety, _ip_is_blocked


BLOCKED_IPS = [
    "10.0.0.1", "172.16.5.5", "192.168.1.1",   # private
    "127.0.0.1",                                 # loopback
    "169.254.169.254",                           # link-local (cloud metadata)
    "0.0.0.0",                                   # unspecified / this-network
    "100.64.0.1",                                # CGNAT
    "::1",                                        # IPv6 loopback
    "::ffff:169.254.169.254",                    # IPv4-mapped обходил старый блок-лист
    "::ffff:127.0.0.1",
]

PUBLIC_IPS = ["8.8.8.8", "1.1.1.1", "93.184.216.34"]


@pytest.mark.parametrize("ip", BLOCKED_IPS)
def test_blocked_ip_is_flagged(ip):
    assert _ip_is_blocked(ipaddress.ip_address(ip)) is True


@pytest.mark.parametrize("ip", PUBLIC_IPS)
def test_public_ip_is_allowed(ip):
    assert _ip_is_blocked(ipaddress.ip_address(ip)) is False


@pytest.mark.parametrize("ip", BLOCKED_IPS)
def test_check_url_safety_rejects_blocked(ip):
    host = f"[{ip}]" if ":" in ip else ip
    ok, reason = check_url_safety(f"http://{host}/hook")
    assert ok is False
    assert reason


@pytest.mark.parametrize("ip", PUBLIC_IPS)
def test_check_url_safety_allows_public(ip):
    ok, _ = check_url_safety(f"https://{ip}/hook")
    assert ok is True


def test_scheme_must_be_http():
    ok, _ = check_url_safety("ftp://8.8.8.8/x")
    assert ok is False


def test_empty_url_rejected():
    ok, _ = check_url_safety("")
    assert ok is False
