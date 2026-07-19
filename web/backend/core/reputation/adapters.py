"""Провайдеры репутации IP. Импорт модуля регистрирует их в реестре base._REGISTRY."""
from typing import Any, Dict, Optional

import httpx

from web.backend.core.reputation.base import RepProvider, RepError, register, normalized

_TIMEOUT = 15.0


async def _get(url: str, *, headers: Optional[Dict[str, str]] = None,
               params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, headers=headers, params=params)
    except httpx.HTTPError as e:
        raise RepError(f"сеть: {e}")
    if r.status_code in (401, 403):
        raise RepError("токен отклонён")
    if r.status_code == 429:
        raise RepError("лимит запросов исчерпан")
    try:
        return r.json()
    except ValueError:
        raise RepError(f"не JSON (HTTP {r.status_code})")


@register
class IpApi(RepProvider):
    slug = "ipapi"
    name = "ip-api.com"
    needs_token = False
    signup_url = "https://ip-api.com"

    async def lookup(self, ip: str, token: Optional[str]) -> Dict[str, Any]:
        d = await _get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,message,countryCode,isp,org,as,mobile,proxy,hosting,query"})
        if isinstance(d, dict) and d.get("status") == "fail":
            raise RepError(str(d.get("message") or "lookup fail"))
        return normalized("ipapi", ip, is_proxy=d.get("proxy"), is_hosting=d.get("hosting"),
                          country=d.get("countryCode"), asn=d.get("as"),
                          org=d.get("org") or d.get("isp"), raw=d)


@register
class IpInfo(RepProvider):
    slug = "ipinfo"
    name = "ipinfo.io"
    needs_token = True
    signup_url = "https://ipinfo.io/signup"

    async def lookup(self, ip: str, token: Optional[str]) -> Dict[str, Any]:
        d = await _get(f"https://ipinfo.io/{ip}/json", params={"token": token or ""})
        if isinstance(d, dict) and d.get("error"):
            err = d["error"]
            raise RepError(str(err.get("message") if isinstance(err, dict) else err))
        priv = d.get("privacy") or {}
        org = str(d.get("org") or "")
        asn = org.split(" ")[0] if org.startswith("AS") else None
        return normalized("ipinfo", ip, is_vpn=priv.get("vpn"), is_proxy=priv.get("proxy"),
                          is_tor=priv.get("tor"), is_hosting=priv.get("hosting"),
                          country=d.get("country"), asn=asn, org=org or None, raw=d)


@register
class Ipqs(RepProvider):
    slug = "ipqs"
    name = "IPQualityScore"
    needs_token = True
    signup_url = "https://www.ipqualityscore.com/create-account"

    async def lookup(self, ip: str, token: Optional[str]) -> Dict[str, Any]:
        d = await _get(f"https://ipqualityscore.com/api/json/ip/{token}/{ip}", params={"strictness": 1})
        if isinstance(d, dict) and d.get("success") is False:
            raise RepError(str(d.get("message") or "lookup fail"))
        return normalized("ipqs", ip, score=d.get("fraud_score"),
                          is_proxy=d.get("proxy"), is_vpn=d.get("vpn") or d.get("active_vpn"),
                          is_tor=d.get("tor"), recent_abuse=d.get("recent_abuse"),
                          country=d.get("country_code"),
                          asn=(f"AS{d.get('ASN')}" if d.get("ASN") else None),
                          org=d.get("ISP"), raw=d)


@register
class AbuseIpdb(RepProvider):
    slug = "abuseipdb"
    name = "AbuseIPDB"
    needs_token = True
    signup_url = "https://www.abuseipdb.com/register"

    async def lookup(self, ip: str, token: Optional[str]) -> Dict[str, Any]:
        d = await _get("https://api.abuseipdb.com/api/v2/check",
                       headers={"Key": token or "", "Accept": "application/json"},
                       params={"ipAddress": ip, "maxAgeInDays": 90})
        data = d.get("data") if isinstance(d, dict) else None
        if not data:
            errs = d.get("errors") if isinstance(d, dict) else None
            raise RepError(str(errs[0].get("detail")) if errs else "нет данных")
        usage = str(data.get("usageType") or "").lower()
        return normalized("abuseipdb", ip, score=data.get("abuseConfidenceScore"),
                          recent_abuse=(data.get("totalReports") or 0) > 0,
                          is_tor=data.get("isTor"),
                          is_hosting=("hosting" in usage or "data center" in usage),
                          country=data.get("countryCode"), org=data.get("isp"), raw=data)
