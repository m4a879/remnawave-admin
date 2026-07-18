"""Config profiles management — proxy to Remnawave Panel API."""
import json
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from web.backend.api.deps import AdminUser, get_client_ip, require_permission
from web.backend.core.audit import write_audit_log

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def list_config_profiles(
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List all config profiles."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_config_profiles()
        payload = result.get("response", {})
        profiles = payload.get("configProfiles", []) if isinstance(payload, dict) else []
        return {"items": profiles, "total": len(profiles)}
    except Exception as e:
        logger.error("Failed to list config profiles: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.get("/inbounds")
async def list_inbounds(
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List all inbounds."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_all_inbounds()
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to list inbounds: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.get("/{profile_uuid}/inbounds")
async def list_profile_inbounds(
    profile_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List inbounds for a specific config profile."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_inbounds_by_profile_uuid(profile_uuid)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to list profile inbounds: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.get("/{profile_uuid}")
async def get_config_profile(
    profile_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """Get a single config profile."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_config_profile_by_uuid(profile_uuid)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to get config profile: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.get("/{profile_uuid}/computed-config")
async def get_computed_config(
    profile_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """Get the computed (expanded) config for a profile."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_config_profile_computed(profile_uuid)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to get computed config: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.get("/{profile_uuid}/versions")
async def list_profile_versions(
    profile_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """История сохранений профиля через встроенный редактор (метаданные)."""
    from shared.database import db_service
    return {"items": await db_service.list_config_versions("profile", profile_uuid)}


@router.get("/versions/{version_id}")
async def get_profile_version(
    version_id: int,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """Содержимое конкретной версии (для отката/диффа в редакторе)."""
    from shared.database import db_service
    version = await db_service.get_config_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


async def _snapshot_profile_baseline(profile_uuid: str) -> None:
    """Перед первым нашим сохранением зафиксировать исходный конфиг панели."""
    from shared.database import db_service
    from shared.api_client import api_client
    existing = await db_service.list_config_versions("profile", profile_uuid, limit=1)
    if existing:
        return
    result = await api_client.get_config_profile_by_uuid(profile_uuid)
    payload = result.get("response", result) or {}
    cfg = payload.get("config") or (payload.get("configProfile") or {}).get("config")
    if cfg:
        await db_service.save_config_version(
            "profile", profile_uuid, json.dumps(cfg, ensure_ascii=False, indent=2),
            entity_name=payload.get("name") or (payload.get("configProfile") or {}).get("name"),
            created_by="baseline",
        )


@router.patch("/{profile_uuid}")
async def update_config_profile(
    profile_uuid: str,
    request: Request,
    config: dict = Body(...),
    admin: AdminUser = Depends(require_permission("resources", "edit")),
):
    """Patch a config profile's xray-config JSON (used by xray-editor page)."""
    # бейзлайн «до первого редактирования» — чтобы всегда был путь назад
    try:
        await _snapshot_profile_baseline(profile_uuid)
    except Exception as e:
        logger.warning("Baseline snapshot for %s failed: %s", profile_uuid, e)

    try:
        from shared.api_client import api_client
        from shared.exceptions import NotFoundError, ServerError, ValidationError
        # Panel expects the JSON payload `{ uuid, config }` to PATCH /api/config-profiles.
        result = await api_client.update_config_profile({"uuid": profile_uuid, "config": config})
    except (ValidationError, ServerError) as e:
        # бизнес-ошибка панели (напр. «All inbounds must have a unique tag») —
        # редактор должен показать её текст, а не generic 502
        logger.warning("Panel rejected config for %s: %s", profile_uuid, e)
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Config profile not found")
    except Exception as e:
        logger.error("Failed to update config profile %s: %s", profile_uuid, e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")

    # снапшот новой версии (дедуп по хэшу внутри)
    try:
        from shared.database import db_service
        await db_service.save_config_version(
            "profile", profile_uuid,
            json.dumps(config, ensure_ascii=False, indent=2),
            created_by=admin.username,
        )
    except Exception as e:
        logger.warning("Version snapshot for %s failed: %s", profile_uuid, e)

    try:
        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="config_profile.update",
            resource="resources",
            resource_id=profile_uuid,
            details=json.dumps({"keys": sorted(list(config.keys()))[:20]}) if isinstance(config, dict) else None,
            ip_address=get_client_ip(request),
        )
    except Exception as e:
        logger.warning("Audit log for config_profile.update failed: %s", e)

    return result.get("response", result)
