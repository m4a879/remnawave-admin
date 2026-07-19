"""Тесты адаптеров репутации IP (нормализация ответов провайдеров)."""
import httpx
import pytest
from unittest.mock import patch

from web.backend.core.reputation import adapters as ad

_REAL = httpx.AsyncClient


def _patched(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL(transport=httpx.MockTransport(handler), **kw)
    return factory


class TestAdapters:
    @pytest.mark.asyncio
    async def test_ipapi(self):
        def h(r):
            return httpx.Response(200, json={"status": "success", "countryCode": "US",
                                             "isp": "Google", "org": "Google LLC",
                                             "as": "AS15169 Google", "proxy": False,
                                             "hosting": True, "query": "8.8.8.8"})
        with patch("httpx.AsyncClient", _patched(h)):
            d = await ad.IpApi().lookup("8.8.8.8", None)
        assert d["is_hosting"] is True and d["country"] == "US"
        assert d["asn"] == "AS15169 Google" and d["provider"] == "ipapi"

    @pytest.mark.asyncio
    async def test_ipqs(self):
        def h(r):
            return httpx.Response(200, json={"success": True, "fraud_score": 75, "proxy": True,
                                             "vpn": True, "tor": False, "recent_abuse": True,
                                             "country_code": "NL", "ASN": 1234, "ISP": "Host"})
        with patch("httpx.AsyncClient", _patched(h)):
            d = await ad.Ipqs().lookup("1.2.3.4", "tok")
        assert d["score"] == 75 and d["is_vpn"] is True and d["asn"] == "AS1234"

    @pytest.mark.asyncio
    async def test_abuseipdb(self):
        def h(r):
            return httpx.Response(200, json={"data": {"abuseConfidenceScore": 40, "totalReports": 3,
                                                      "isTor": False, "countryCode": "DE",
                                                      "usageType": "Data Center/Web Hosting/Transit",
                                                      "isp": "Hetzner"}})
        with patch("httpx.AsyncClient", _patched(h)):
            d = await ad.AbuseIpdb().lookup("5.6.7.8", "tok")
        assert d["score"] == 40 and d["recent_abuse"] is True and d["is_hosting"] is True

    @pytest.mark.asyncio
    async def test_ipqs_error(self):
        def h(r):
            return httpx.Response(200, json={"success": False, "message": "Invalid key"})
        with patch("httpx.AsyncClient", _patched(h)):
            with pytest.raises(ad.RepError, match="Invalid"):
                await ad.Ipqs().lookup("1.2.3.4", "bad")
