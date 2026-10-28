from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from urllib import error as urlerror
from urllib import request as urlrequest
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import Client, create_client

import config


APP_STATE_KEY = "minerbytsfree_runtime"
BOT_BUNDLE_KEY = "minerbytsfree_bot_bundle"
FLASH_BOT_BUNDLE_KEY = "zuncia_bot_bundle"
AZTLACOIN_BOT_BUNDLE_KEY = "aztlacoin_bot_bundle"
CROPCROPS_BOT_BUNDLE_KEY = "cryptocrops_bot_bundle"
LIGHTNING_BOT_BUNDLE_KEY = "lightningminer_bot_bundle"
CROPCROPS_SCRIPT_PACKAGES_KEY = "cryptocrops_script_packages"
LIGHTNING_SCRIPT_PACKAGES_KEY = "lightningminer_script_packages"
FLASH_APP_KEY = "zuncia"
AZTLACOIN_APP_KEY = "aztlacoin"
CROPCROPS_APP_KEY = "cryptocrops"
LIGHTNING_APP_KEY = "lightningminer"

app = FastAPI(title=config.APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS if config.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE: Client | None = None
LAST_SYNC_EPOCH = 0.0

RUNTIME_STATE: dict[str, Any] = {
    "project": config.PROJECT_NAME,
    "status": "booting",
    "started_at": "",
    "licenses": [],
    "bot_bundle": {"name": "", "content": "", "hash": "", "version": 0, "updated_at": ""},
    "settings": {"heartbeat_seconds": 30, "bind_mode": "first_account"},
    FLASH_APP_KEY: {
        "licenses": [],
        "bot_bundle": {"name": "", "content": "", "hash": "", "version": 0, "updated_at": ""},
        "settings": {"heartbeat_seconds": 30, "bind_mode": "first_account"},
    },
    AZTLACOIN_APP_KEY: {
        "licenses": [],
        "bot_bundle": {"name": "", "content": "", "hash": "", "version": 0, "updated_at": ""},
        "settings": {"heartbeat_seconds": 30, "bind_mode": "first_account"},
    },
    CROPCROPS_APP_KEY: {
        "licenses": [],
        "bot_bundle": {"name": "", "content": "", "hash": "", "version": 0, "updated_at": ""},
        "settings": {"heartbeat_seconds": 30, "bind_mode": "first_account"},
        "telegram_captchas": {},
    },
    LIGHTNING_APP_KEY: {
        "licenses": [],
        "bot_bundle": {"name": "", "content": "", "hash": "", "version": 0, "updated_at": ""},
        "settings": {"heartbeat_seconds": 30, "bind_mode": "first_account"},
        "script_packages": {},
    },
}


class LicenseCreatePayload(BaseModel):
    name: str = "User"
    key: str | None = None
    active: bool = True
    multi_account: bool = False
    allowed_client_id: str | None = None


class BotUploadPayload(BaseModel):
    file_name: str = "botfree.txt"
    content: str


class ScriptPackagePayload(BaseModel):
    license_id: str
    client_id: str
    script_id: str
    content: str


class AuthPayload(BaseModel):
    license_key: str
    client_id: str
    script_id: str | None = None
    account_id: str | None = None
    page: str | None = None
    user_agent: str | None = None


class HeartbeatPayload(BaseModel):
    token: str
    client_id: str
    script_id: str | None = None
    account_id: str | None = None
    page: str | None = None


class TamperPayload(BaseModel):
    token: str | None = None
    license_key: str | None = None
    client_id: str | None = None
    script_id: str | None = None
    account_id: str | None = None
    reason: str = "f12"
    source: str = "client"
    page: str | None = None
    user_agent: str | None = None


@app.on_event("startup")
def startup_event() -> None:
    global SUPABASE
    RUNTIME_STATE["status"] = "ready"
    RUNTIME_STATE["started_at"] = utc_now()
    SUPABASE = build_supabase_client()
    load_state()
    load_bot_bundle()
    load_script_packages()
    ensure_shapes()


def app_state(app_key: str = "minerbyts") -> dict[str, Any]:
    ensure_shapes()
    if app_key == FLASH_APP_KEY:
        return RUNTIME_STATE[FLASH_APP_KEY]
    if app_key == AZTLACOIN_APP_KEY:
        return RUNTIME_STATE[AZTLACOIN_APP_KEY]
    if app_key == CROPCROPS_APP_KEY:
        return RUNTIME_STATE[CROPCROPS_APP_KEY]
    if app_key == LIGHTNING_APP_KEY:
        return RUNTIME_STATE[LIGHTNING_APP_KEY]
    return RUNTIME_STATE


def app_label(app_key: str = "minerbyts") -> str:
    if app_key == FLASH_APP_KEY:
        return "zuncia"
    if app_key == AZTLACOIN_APP_KEY:
        return "aztlacoin"
    if app_key == CROPCROPS_APP_KEY:
        return "cryptocrops"
    if app_key == LIGHTNING_APP_KEY:
        return "lightningminer"
    return "minerbyts"


@app.get("/")
def index() -> dict[str, Any]:
    return {"success": True, "project": config.PROJECT_NAME, "message": "minerbytsfree server aktif"}


@app.get("/health")
def health() -> dict[str, Any]:
    ensure_shapes()
    return {
        "success": True,
        "project": config.PROJECT_NAME,
        "status": RUNTIME_STATE.get("status", "unknown"),
        "time": utc_now(),
        "supabase": bool(SUPABASE),
        "license_count": len(RUNTIME_STATE.get("licenses") or []),
        "bot_uploaded": bool((RUNTIME_STATE.get("bot_bundle") or {}).get("content")),
        "bot_hash": (RUNTIME_STATE.get("bot_bundle") or {}).get("hash", ""),
        "last_sync": RUNTIME_STATE.get("last_sync", ""),
        "storage_error": RUNTIME_STATE.get("storage_error", ""),
    }


@app.post("/api/auth")
def api_auth(payload: AuthPayload) -> dict[str, Any]:
    ensure_shapes()
    lic = find_license_by_key(payload.license_key)
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
    if lic.get("tamper_detected"):
        return {"success": False, "error": "Connect Nexus."}
    if not lic.get("active", True):
        return {"success": False, "error": "Lisans pasif"}

    client_error = validate_client_binding(lic, payload.client_id, payload.script_id)
    if client_error:
        return {"success": False, "error": client_error}

    account_error = validate_account_binding(lic, payload.account_id)
    if account_error:
        return {"success": False, "error": account_error}

    token = secrets.token_urlsafe(32)
    lic["session_token"] = token
    lic["online"] = True
    lic["last_seen_at"] = utc_now()
    lic["last_page"] = payload.page or ""
    lic["last_user_agent"] = payload.user_agent or ""
    save_state(force=True)
    return {
        "success": True,
        "token": token,
        "license": sanitize_license(lic),
        "settings": RUNTIME_STATE.get("settings", {}),
        "bot": summarize_bot_bundle(),
    }


@app.post("/api/heartbeat")
def api_heartbeat(payload: HeartbeatPayload) -> dict[str, Any]:
    lic = find_license_by_session(payload.token)
    if not lic:
        return {"success": False, "error": "Oturum gecersiz"}
    if lic.get("tamper_detected"):
        return {"success": False, "error": "Connect Nexus."}
    binding_error = validate_runtime_binding(lic, payload.client_id, payload.script_id, payload.account_id)
    if binding_error:
        return {"success": False, "error": binding_error}
    lic["online"] = True
    lic["last_seen_at"] = utc_now()
    lic["last_page"] = payload.page or ""
    return {"success": True, "server_time": utc_now(), "settings": RUNTIME_STATE.get("settings", {})}


@app.post("/api/tamper/report")
def api_tamper_report(payload: TamperPayload) -> dict[str, Any]:
    return api_tamper_report_for_app(payload, "minerbyts")


@app.get("/api/tamper/report.gif")
def api_tamper_report_beacon(
    token: str | None = None,
    license_key: str | None = None,
    client_id: str | None = None,
    script_id: str | None = None,
    account_id: str | None = None,
    reason: str = "f12",
    source: str = "beacon",
    page: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    return api_tamper_report_for_app(TamperPayload(
        token=token,
        license_key=license_key,
        client_id=client_id,
        script_id=script_id,
        account_id=account_id,
        reason=reason,
        source=source,
        page=page,
        user_agent=user_agent,
    ), "minerbyts")


@app.get("/api/bot/bundle")
def api_bot_bundle(token: str, client_id: str, script_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
    lic = find_license_by_session(token)
    if not lic:
        return {"success": False, "error": "Oturum gecersiz"}
    if lic.get("tamper_detected"):
        return {"success": False, "error": "Connect Nexus."}
    binding_error = validate_runtime_binding(lic, client_id, script_id, account_id)
    if binding_error:
        return {"success": False, "error": binding_error}
    bundle = RUNTIME_STATE.get("bot_bundle") or {}
    content = str(bundle.get("content") or "")
    if not content:
        return {"success": False, "error": "Bot henuz yuklenmedi"}
    lic["last_seen_at"] = utc_now()
    save_state(force=False)
    return {
        "success": True,
        "name": bundle.get("name") or "botfree.txt",
        "version": bundle.get("version") or 0,
        "hash": bundle.get("hash") or "",
        "encoding": "xor-base64",
        "encrypted": encrypt_for_client(content, client_id),
    }


@app.get("/admin/state")
def admin_state(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    return {"success": True, "state": RUNTIME_STATE}


@app.get("/admin/licenses")
def admin_licenses(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    mark_stale_offline()
    return {"success": True, "licenses": [sanitize_license(x) for x in RUNTIME_STATE.get("licenses", [])]}


@app.post("/admin/license/create")
def admin_license_create(payload: LicenseCreatePayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    key = (payload.key or "").strip() or generate_license_key()
    if find_license_by_key(key):
        return {"success": False, "error": "Bu key zaten var"}
    now = utc_now()
    lic = {
        "id": secrets.token_hex(8),
        "name": (payload.name or "User").strip(),
        "key": key,
        "active": bool(payload.active),
        "multi_account": bool(payload.multi_account),
        "account_id": "",
        "client_id": "",
        "script_id": "",
        "allowed_client_id": (payload.allowed_client_id or "").strip(),
        "session_token": "",
        "online": False,
        "created_at": now,
        "last_seen_at": "",
        "last_page": "",
        "tamper_detected": False,
        "tamper_reason": "",
        "tamper_at": "",
        "tamper_report": {},
    }
    RUNTIME_STATE["licenses"].insert(0, lic)
    save_state(force=True)
    return {"success": True, "license": sanitize_license(lic)}


@app.post("/admin/license/toggle")
def admin_license_toggle(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    lic = find_license_by_id(str(payload.get("license_id") or ""))
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
    if "active" in payload:
        if bool(payload.get("active")) and lic.get("tamper_detected"):
            return {"success": False, "error": "F12 damgasi temizlenmeden aktif edilemez"}
        lic["active"] = bool(payload.get("active"))
    if "multi_account" in payload:
        lic["multi_account"] = bool(payload.get("multi_account"))
    if payload.get("reset_account"):
        lic["account_id"] = ""
    save_state(force=True)
    return {"success": True, "license": sanitize_license(lic)}


@app.post("/admin/license/key")
def admin_license_key(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    lic = find_license_by_id(str(payload.get("license_id") or ""))
    new_key = str(payload.get("key") or "").strip()
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
    if not new_key:
        return {"success": False, "error": "Key bos olamaz"}
    other = find_license_by_key(new_key)
    if other and other.get("id") != lic.get("id"):
        return {"success": False, "error": "Bu key baska lisansta var"}
    lic["key"] = new_key
    save_state(force=True)
    return {"success": True, "license": sanitize_license(lic)}


@app.post("/admin/license/delete")
def admin_license_delete(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    license_id = str(payload.get("license_id") or "")
    before = len(RUNTIME_STATE.get("licenses") or [])
    RUNTIME_STATE["licenses"] = [x for x in RUNTIME_STATE.get("licenses", []) if x.get("id") != license_id]
    save_state(force=True)
    return {"success": True, "deleted": before - len(RUNTIME_STATE["licenses"])}


@app.post("/admin/license/tamper-clear")
def admin_license_tamper_clear(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_tamper_clear_for_app(payload, x_admin_token, "minerbyts")


@app.post("/admin/bot/upload")
def admin_bot_upload(payload: BotUploadPayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    content = str(payload.content or "")
    if not content.strip():
        return {"success": False, "error": "Bot icerigi bos"}
    bundle = {
        "name": payload.file_name or "botfree.txt",
        "content": content,
        "hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "version": int((RUNTIME_STATE.get("bot_bundle") or {}).get("version") or 0) + 1,
        "updated_at": utc_now(),
    }
    RUNTIME_STATE["bot_bundle"] = bundle
    save_bot_bundle(force=True)
    save_state(force=True)
    return {"success": True, "bot": summarize_bot_bundle()}


@app.get("/zuncia/health")
def flash_health() -> dict[str, Any]:
    ensure_shapes()
    state = app_state(FLASH_APP_KEY)
    bundle = state.get("bot_bundle") or {}
    return {
        "success": True,
        "project": "zuncia",
        "status": RUNTIME_STATE.get("status", "unknown"),
        "time": utc_now(),
        "supabase": bool(SUPABASE),
        "license_count": len(state.get("licenses") or []),
        "bot_uploaded": bool(bundle.get("content")),
        "bot_hash": bundle.get("hash", ""),
        "last_sync": RUNTIME_STATE.get("last_sync", ""),
        "storage_error": RUNTIME_STATE.get("storage_error", ""),
        "last_tamper_lock": state.get("last_tamper_lock", {}),
        "last_tamper_miss": state.get("last_tamper_miss", {}),
    }


@app.post("/zuncia/api/auth")
def flash_api_auth(payload: AuthPayload) -> dict[str, Any]:
    return api_auth_for_app(payload, FLASH_APP_KEY)


@app.post("/zuncia/api/heartbeat")
def flash_api_heartbeat(payload: HeartbeatPayload) -> dict[str, Any]:
    return api_heartbeat_for_app(payload, FLASH_APP_KEY)


@app.post("/zuncia/api/tamper/report")
def flash_api_tamper_report(payload: TamperPayload) -> dict[str, Any]:
    return api_tamper_report_for_app(payload, FLASH_APP_KEY)


@app.get("/zuncia/api/tamper/report.gif")
def flash_api_tamper_report_beacon(
    token: str | None = None,
    license_key: str | None = None,
    client_id: str | None = None,
    script_id: str | None = None,
    account_id: str | None = None,
    reason: str = "f12",
    source: str = "beacon",
    page: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    return api_tamper_report_for_app(TamperPayload(
        token=token,
        license_key=license_key,
        client_id=client_id,
        script_id=script_id,
        account_id=account_id,
        reason=reason,
        source=source,
        page=page,
        user_agent=user_agent,
    ), FLASH_APP_KEY)


@app.get("/zuncia/api/bot/bundle")
def flash_api_bot_bundle(token: str, client_id: str, script_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
    return api_bot_bundle_for_app(token, client_id, script_id, account_id, FLASH_APP_KEY)


@app.get("/zuncia/admin/state")
def flash_admin_state(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    return {"success": True, "state": app_state(FLASH_APP_KEY)}


@app.get("/zuncia/admin/licenses")
def flash_admin_licenses(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    mark_stale_offline()
    return {"success": True, "licenses": [sanitize_license(x) for x in app_state(FLASH_APP_KEY).get("licenses", [])]}


@app.post("/zuncia/admin/license/create")
def flash_admin_license_create(payload: LicenseCreatePayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_create_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.post("/zuncia/admin/license/toggle")
def flash_admin_license_toggle(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_toggle_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.post("/zuncia/admin/license/key")
def flash_admin_license_key(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_key_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.post("/zuncia/admin/license/delete")
def flash_admin_license_delete(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_delete_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.post("/zuncia/admin/license/tamper-clear")
def flash_admin_license_tamper_clear(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_tamper_clear_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.post("/zuncia/admin/bot/upload")
def flash_admin_bot_upload(payload: BotUploadPayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_bot_upload_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.get("/aztlacoin/health")
def aztlacoin_health() -> dict[str, Any]:
    ensure_shapes()
    state = app_state(AZTLACOIN_APP_KEY)
    bundle = state.get("bot_bundle") or {}
    return {
        "success": True,
        "project": "aztlacoin",
        "status": RUNTIME_STATE.get("status", "unknown"),
        "time": utc_now(),
        "supabase": bool(SUPABASE),
        "license_count": len(state.get("licenses") or []),
        "bot_uploaded": bool(bundle.get("content")),
        "bot_hash": bundle.get("hash", ""),
        "last_sync": RUNTIME_STATE.get("last_sync", ""),
        "storage_error": RUNTIME_STATE.get("storage_error", ""),
        "last_tamper_lock": state.get("last_tamper_lock", {}),
        "last_tamper_miss": state.get("last_tamper_miss", {}),
    }


@app.post("/aztlacoin/api/auth")
def aztlacoin_api_auth(payload: AuthPayload) -> dict[str, Any]:
    return api_auth_for_app(payload, AZTLACOIN_APP_KEY)


@app.post("/aztlacoin/api/heartbeat")
def aztlacoin_api_heartbeat(payload: HeartbeatPayload) -> dict[str, Any]:
    return api_heartbeat_for_app(payload, AZTLACOIN_APP_KEY)


@app.post("/aztlacoin/api/tamper/report")
def aztlacoin_api_tamper_report(payload: TamperPayload) -> dict[str, Any]:
    return api_tamper_report_for_app(payload, AZTLACOIN_APP_KEY)


@app.get("/aztlacoin/api/tamper/report.gif")
def aztlacoin_api_tamper_report_beacon(
    token: str | None = None,
    license_key: str | None = None,
    client_id: str | None = None,
    script_id: str | None = None,
    account_id: str | None = None,
    reason: str = "f12",
    source: str = "beacon",
    page: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    return api_tamper_report_for_app(TamperPayload(
        token=token,
        license_key=license_key,
        client_id=client_id,
        script_id=script_id,
        account_id=account_id,
        reason=reason,
        source=source,
        page=page,
        user_agent=user_agent,
    ), AZTLACOIN_APP_KEY)


@app.get("/aztlacoin/api/bot/bundle")
def aztlacoin_api_bot_bundle(token: str, client_id: str, script_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
    return api_bot_bundle_for_app(token, client_id, script_id, account_id, AZTLACOIN_APP_KEY)


@app.get("/aztlacoin/admin/state")
def aztlacoin_admin_state(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    return {"success": True, "state": app_state(AZTLACOIN_APP_KEY)}


@app.get("/aztlacoin/admin/licenses")
def aztlacoin_admin_licenses(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    mark_stale_offline()
    return {"success": True, "licenses": [sanitize_license(x) for x in app_state(AZTLACOIN_APP_KEY).get("licenses", [])]}


@app.post("/aztlacoin/admin/license/create")
def aztlacoin_admin_license_create(payload: LicenseCreatePayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_create_for_app(payload, x_admin_token, AZTLACOIN_APP_KEY)


@app.post("/aztlacoin/admin/license/toggle")
def aztlacoin_admin_license_toggle(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_toggle_for_app(payload, x_admin_token, AZTLACOIN_APP_KEY)


@app.post("/aztlacoin/admin/license/key")
def aztlacoin_admin_license_key(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_key_for_app(payload, x_admin_token, AZTLACOIN_APP_KEY)


@app.post("/aztlacoin/admin/license/delete")
def aztlacoin_admin_license_delete(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_delete_for_app(payload, x_admin_token, AZTLACOIN_APP_KEY)


@app.post("/aztlacoin/admin/license/tamper-clear")
def aztlacoin_admin_license_tamper_clear(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_tamper_clear_for_app(payload, x_admin_token, AZTLACOIN_APP_KEY)


@app.post("/aztlacoin/admin/bot/upload")
def aztlacoin_admin_bot_upload(payload: BotUploadPayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_bot_upload_for_app(payload, x_admin_token, AZTLACOIN_APP_KEY)


@app.get("/lightningminer/health")
def lightningminer_health() -> dict[str, Any]:
    ensure_shapes()
    state = app_state(LIGHTNING_APP_KEY)
    bundle = state.get("bot_bundle") or {}
    return {
        "success": True,
        "project": LIGHTNING_APP_KEY,
        "status": RUNTIME_STATE.get("status", "unknown"),
        "time": utc_now(),
        "supabase": bool(SUPABASE),
        "license_count": len(state.get("licenses") or []),
        "bot_uploaded": bool(bundle.get("content")),
        "bot_hash": bundle.get("hash", ""),
        "last_tamper_lock": state.get("last_tamper_lock", {}),
        "last_tamper_miss": state.get("last_tamper_miss", {}),
    }


@app.post("/lightningminer/api/auth")
def lightningminer_api_auth(payload: AuthPayload) -> dict[str, Any]:
    return api_auth_for_app(payload, LIGHTNING_APP_KEY)


@app.post("/lightningminer/api/heartbeat")
def lightningminer_api_heartbeat(payload: HeartbeatPayload) -> dict[str, Any]:
    return api_heartbeat_for_app(payload, LIGHTNING_APP_KEY)


@app.post("/lightningminer/api/tamper/report")
def lightningminer_api_tamper(payload: TamperPayload) -> dict[str, Any]:
    return api_tamper_report_for_app(payload, LIGHTNING_APP_KEY)


@app.get("/lightningminer/api/tamper/report.gif")
def lightningminer_api_tamper_beacon(
    token: str | None = None,
    license_key: str | None = None,
    client_id: str | None = None,
    script_id: str | None = None,
    account_id: str | None = None,
    reason: str = "f12",
    source: str = "beacon",
    page: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    return api_tamper_report_for_app(TamperPayload(
        token=token,
        license_key=license_key,
        client_id=client_id,
        script_id=script_id,
        account_id=account_id,
        reason=reason,
        source=source,
        page=page,
        user_agent=user_agent,
    ), LIGHTNING_APP_KEY)


@app.get("/lightningminer/api/bot/bundle")
def lightningminer_api_bundle(token: str, client_id: str, script_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
    return api_bot_bundle_for_app(token, client_id, script_id, account_id, LIGHTNING_APP_KEY)


@app.get("/lightningminer/admin/licenses")
def lightningminer_admin_licenses(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    mark_stale_offline()
    return {"success": True, "licenses": [sanitize_license(x) for x in app_state(LIGHTNING_APP_KEY).get("licenses", [])]}


@app.post("/lightningminer/admin/license/create")
def lightningminer_admin_license_create(payload: LicenseCreatePayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_create_for_app(payload, x_admin_token, LIGHTNING_APP_KEY)


@app.post("/lightningminer/admin/license/toggle")
def lightningminer_admin_license_toggle(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_toggle_for_app(payload, x_admin_token, LIGHTNING_APP_KEY)


@app.post("/lightningminer/admin/license/key")
def lightningminer_admin_license_key(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_key_for_app(payload, x_admin_token, LIGHTNING_APP_KEY)


@app.post("/lightningminer/admin/license/delete")
def lightningminer_admin_license_delete(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_delete_for_app(payload, x_admin_token, LIGHTNING_APP_KEY)


@app.post("/lightningminer/admin/license/tamper-clear")
def lightningminer_admin_license_tamper_clear(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_tamper_clear_for_app(payload, x_admin_token, LIGHTNING_APP_KEY)


@app.post("/lightningminer/admin/bot/upload")
def lightningminer_admin_bot_upload(payload: BotUploadPayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_bot_upload_for_app(payload, x_admin_token, LIGHTNING_APP_KEY)


@app.post("/lightningminer/admin/script/upload")
def lightningminer_admin_script_upload(payload: ScriptPackagePayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    state = app_state(LIGHTNING_APP_KEY)
    lic = find_license_by_id(payload.license_id, LIGHTNING_APP_KEY)
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
    if str(lic.get("allowed_client_id") or "") != str(payload.client_id or ""):
        return {"success": False, "error": "Script lisans kimligiyle eslesmiyor"}
    if not payload.content.strip() or len(payload.content) > 2_000_000:
        return {"success": False, "error": "Gecersiz script paketi"}
    state.setdefault("script_packages", {})[str(payload.script_id)] = {
        "license_id": str(payload.license_id),
        "client_id": str(payload.client_id),
        "content": payload.content,
        "updated_at": utc_now(),
    }
    save_script_packages(LIGHTNING_APP_KEY)
    return {"success": True, "script_id": payload.script_id}


@app.get("/lightningminer/script/{script_id}.user.js")
def lightningminer_script_update(script_id: str, client_id: str) -> Response:
    package = (app_state(LIGHTNING_APP_KEY).get("script_packages") or {}).get(script_id) or {}
    if str(package.get("client_id") or "") != str(client_id or ""):
        raise HTTPException(status_code=404, detail="Script bulunamadi")
    content = str(package.get("content") or "")
    if not content:
        raise HTTPException(status_code=404, detail="Script bulunamadi")
    return Response(content=content, media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/cryptocrops/health")
def cryptocrops_health() -> dict[str, Any]:
    ensure_shapes()
    state = app_state(CROPCROPS_APP_KEY)
    bundle = state.get("bot_bundle") or {}
    return {"success": True, "project": "cryptocrops", "status": RUNTIME_STATE.get("status", "unknown"), "time": utc_now(), "supabase": bool(SUPABASE), "license_count": len(state.get("licenses") or []), "bot_uploaded": bool(bundle.get("content")), "bot_hash": bundle.get("hash", "")}


@app.post("/cryptocrops/api/auth")
def cryptocrops_api_auth(payload: AuthPayload) -> dict[str, Any]:
    return api_auth_for_app(payload, CROPCROPS_APP_KEY)


@app.post("/cryptocrops/api/heartbeat")
def cryptocrops_api_heartbeat(payload: HeartbeatPayload) -> dict[str, Any]:
    return api_heartbeat_for_app(payload, CROPCROPS_APP_KEY)


@app.post("/cryptocrops/api/tamper/report")
def cryptocrops_api_tamper(payload: TamperPayload) -> dict[str, Any]:
    return api_tamper_report_for_app(payload, CROPCROPS_APP_KEY)


@app.get("/cryptocrops/api/bot/bundle")
def cryptocrops_api_bundle(token: str, client_id: str, script_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
    return api_bot_bundle_for_app(token, client_id, script_id, account_id, CROPCROPS_APP_KEY)


@app.get("/cryptocrops/admin/licenses")
def cryptocrops_admin_licenses(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    mark_stale_offline()
    return {"success": True, "licenses": [sanitize_license(x) for x in app_state(CROPCROPS_APP_KEY).get("licenses", [])]}


@app.post("/cryptocrops/admin/license/create")
def cryptocrops_admin_license_create(payload: LicenseCreatePayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_create_for_app(payload, x_admin_token, CROPCROPS_APP_KEY)


@app.post("/cryptocrops/admin/license/toggle")
def cryptocrops_admin_license_toggle(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_toggle_for_app(payload, x_admin_token, CROPCROPS_APP_KEY)


@app.post("/cryptocrops/admin/license/key")
def cryptocrops_admin_license_key(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_key_for_app(payload, x_admin_token, CROPCROPS_APP_KEY)


@app.post("/cryptocrops/admin/license/delete")
def cryptocrops_admin_license_delete(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_delete_for_app(payload, x_admin_token, CROPCROPS_APP_KEY)


@app.post("/cryptocrops/admin/license/tamper-clear")
def cryptocrops_admin_license_tamper_clear(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_tamper_clear_for_app(payload, x_admin_token, CROPCROPS_APP_KEY)


@app.post("/cryptocrops/admin/bot/upload")
def cryptocrops_admin_bot_upload(payload: BotUploadPayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_bot_upload_for_app(payload, x_admin_token, CROPCROPS_APP_KEY)


@app.post("/cryptocrops/admin/script/upload")
def cryptocrops_admin_script_upload(payload: ScriptPackagePayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    state = app_state(CROPCROPS_APP_KEY)
    lic = find_license_by_id(payload.license_id, CROPCROPS_APP_KEY)
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
    if str(lic.get("allowed_client_id") or "") != str(payload.client_id or ""):
        return {"success": False, "error": "Script lisans kimligiyle eslesmiyor"}
    if not payload.content.strip() or len(payload.content) > 2_000_000:
        return {"success": False, "error": "Gecersiz script paketi"}
    packages = state.setdefault("script_packages", {})
    packages[str(payload.script_id)] = {
        "license_id": str(payload.license_id),
        "client_id": str(payload.client_id),
        "content": payload.content,
        "updated_at": utc_now(),
    }
    save_script_packages(CROPCROPS_APP_KEY)
    return {"success": True, "script_id": payload.script_id}


@app.get("/cryptocrops/script/{script_id}.user.js")
def cryptocrops_script_update(script_id: str, client_id: str) -> Response:
    package = (app_state(CROPCROPS_APP_KEY).get("script_packages") or {}).get(script_id) or {}
    if str(package.get("client_id") or "") != str(client_id or ""):
        raise HTTPException(status_code=404, detail="Script bulunamadi")
    content = str(package.get("content") or "")
    if not content:
        raise HTTPException(status_code=404, detail="Script bulunamadi")
    return Response(content=content, media_type="application/javascript", headers={"Cache-Control": "no-store"})


def telegram_api_call(token: str, method: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    token = str(token or "").strip()
    if not token:
        return False, {"error": "Telegram bot token bos"}
    try:
        req = urlrequest.Request(
            f"https://api.telegram.org/bot{token}/{method}",
            data=json.dumps(payload or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        return bool(data.get("ok")), data
    except (urlerror.HTTPError, urlerror.URLError) as exc:
        return False, {"error": str(exc)}
    except Exception as exc:
        return False, {"error": str(exc)}


def require_cryptocrops_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    lic = find_license_by_session(str(payload.get("token") or ""), CROPCROPS_APP_KEY)
    if not lic or lic.get("active") is False or lic.get("tamper_detected"):
        raise HTTPException(status_code=403, detail="Oturum gecersiz")
    binding_error = validate_runtime_binding(
        lic,
        str(payload.get("client_id") or ""),
        str(payload.get("script_id") or ""),
        str(payload.get("account_id") or ""),
    )
    if binding_error:
        raise HTTPException(status_code=403, detail=binding_error)
    return lic


def cleanup_cryptocrops_captchas() -> dict[str, Any]:
    sessions = app_state(CROPCROPS_APP_KEY).setdefault("telegram_captchas", {})
    cutoff = time.time() - 900
    for captcha_id, session in list(sessions.items()):
        if float((session or {}).get("created_epoch") or 0) < cutoff:
            sessions.pop(captcha_id, None)
    while len(sessions) > 30:
        oldest = min(sessions, key=lambda key: float((sessions.get(key) or {}).get("created_epoch") or 0))
        sessions.pop(oldest, None)
    return sessions


@app.post("/cryptocrops/api/telegram/register")
def cryptocrops_telegram_register(payload: dict[str, Any]) -> dict[str, Any]:
    lic = require_cryptocrops_runtime(payload)
    bot_token = str(payload.get("telegram_token") or "").strip()
    chat_id = str(payload.get("telegram_chat_id") or "").strip()
    if not bot_token and not chat_id:
        lic["telegram_token"] = ""
        lic["telegram_chat_id"] = ""
        lic["telegram_bot_username"] = ""
        save_state(force=True)
        return {"success": True, "configured": False}
    if not bot_token or not chat_id:
        raise HTTPException(status_code=400, detail="Bot token ve Chat ID birlikte gerekli")
    ok, me = telegram_api_call(bot_token, "getMe", {})
    if not ok:
        raise HTTPException(status_code=400, detail="Telegram bot token gecersiz")
    ok, chat = telegram_api_call(bot_token, "getChat", {"chat_id": chat_id})
    chat_row = chat.get("result") if isinstance(chat, dict) else {}
    if not ok or not isinstance(chat_row, dict):
        raise HTTPException(status_code=400, detail="Ozel sohbet bulunamadi; bota once /start gonder")
    if str(chat_row.get("type") or "").lower() != "private":
        raise HTTPException(status_code=400, detail="Sadece ozel Telegram sohbeti kabul edilir; grup ve kanal yasak")
    if str(chat_row.get("id") or "") != chat_id:
        raise HTTPException(status_code=400, detail="Chat ID dogrulanamadi")
    lic["telegram_token"] = bot_token
    lic["telegram_chat_id"] = chat_id
    lic["telegram_bot_username"] = str((me.get("result") or {}).get("username") or "")
    lic["telegram_connected_at"] = utc_now()
    save_state(force=True)
    telegram_api_call(bot_token, "sendMessage", {
        "chat_id": chat_id,
        "text": "✅ Nexus CryptoCrops baglandi. CAPTCHA bildirimleri yalnizca bu ozel sohbete gelecek.",
    })
    return {"success": True, "configured": True, "bot_username": lic["telegram_bot_username"]}


@app.post("/cryptocrops/api/telegram/captcha/create")
def cryptocrops_telegram_captcha_create(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    lic = require_cryptocrops_runtime(payload)
    bot_token = str(lic.get("telegram_token") or "").strip()
    chat_id = str(lic.get("telegram_chat_id") or "").strip()
    if not bot_token or not chat_id:
        raise HTTPException(status_code=400, detail="Telegram ayarlanmamis")
    site_key = str(payload.get("site_key") or "").strip()
    if not site_key or len(site_key) > 180 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in site_key):
        raise HTTPException(status_code=400, detail="hCaptcha site key gecersiz")
    captcha_id = "cc_" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")
    sessions = cleanup_cryptocrops_captchas()
    solve_url = str(request.base_url).rstrip("/") + f"/cryptocrops/telegram/captcha/{captcha_id}"
    session = {
        "captcha_id": captcha_id,
        "license_id": str(lic.get("id") or ""),
        "site_key": site_key,
        "kind": str(payload.get("kind") or "captcha")[:40],
        "page_url": str(payload.get("page_url") or "")[:500],
        "status": "waiting",
        "captcha_token": "",
        "created_at": utc_now(),
        "created_epoch": time.time(),
        "telegram_message_id": "",
    }
    sessions[captcha_id] = session
    save_state(force=True)
    ok, sent = telegram_api_call(bot_token, "sendMessage", {
        "chat_id": chat_id,
        "text": "🚨 CryptoCrops CAPTCHA acildi. Asagidaki butondan dogrulamayi tamamla.",
        "reply_markup": {"inline_keyboard": [[{"text": "🧩 CAPTCHA COZ", "url": solve_url}]]},
        "disable_web_page_preview": True,
    })
    if not ok:
        sessions.pop(captcha_id, None)
        save_state(force=True)
        raise HTTPException(status_code=400, detail="Telegram mesaji gonderilemedi")
    session["telegram_message_id"] = str((sent.get("result") or {}).get("message_id") or "")
    save_state(force=True)
    return {"success": True, "captcha_id": captcha_id, "poll_ms": 1800}


@app.get("/cryptocrops/api/telegram/captcha/status")
def cryptocrops_telegram_captcha_status(token: str, captcha_id: str, client_id: str = "", script_id: str = "", account_id: str = "") -> dict[str, Any]:
    lic = require_cryptocrops_runtime({"token": token, "client_id": client_id, "script_id": script_id, "account_id": account_id})
    session = cleanup_cryptocrops_captchas().get(str(captcha_id or "")) or {}
    if not session or str(session.get("license_id") or "") != str(lic.get("id") or ""):
        raise HTTPException(status_code=404, detail="CAPTCHA oturumu bulunamadi")
    solved = session.get("status") == "solved" and bool(session.get("captcha_token"))
    if solved:
        session["status"] = "consumed"
        save_state(force=True)
    return {"success": True, "status": "solved" if solved else session.get("status", "waiting"), "solved": solved, "captcha_token": session.get("captcha_token", "") if solved else ""}


@app.post("/cryptocrops/api/telegram/captcha/solve")
def cryptocrops_telegram_captcha_solve(payload: dict[str, Any]) -> dict[str, Any]:
    captcha_id = str(payload.get("captcha_id") or "").strip()
    captcha_token = str(payload.get("captcha_token") or "").strip()
    session = cleanup_cryptocrops_captchas().get(captcha_id) or {}
    if not session:
        raise HTTPException(status_code=404, detail="CAPTCHA oturumu bulunamadi")
    if len(captcha_token) < 20:
        raise HTTPException(status_code=400, detail="CAPTCHA token gecersiz")
    if session.get("status") not in {"waiting", "solved"}:
        raise HTTPException(status_code=410, detail="CAPTCHA oturumu kapandi")
    session["captcha_token"] = captcha_token
    session["status"] = "solved"
    session["solved_at"] = utc_now()
    lic = find_license_by_id(str(session.get("license_id") or ""), CROPCROPS_APP_KEY) or {}
    message_id = str(session.get("telegram_message_id") or "")
    if message_id and lic.get("telegram_token") and lic.get("telegram_chat_id"):
        telegram_api_call(str(lic["telegram_token"]), "deleteMessage", {"chat_id": str(lic["telegram_chat_id"]), "message_id": message_id})
    save_state(force=True)
    return {"success": True}


@app.get("/cryptocrops/telegram/captcha/{captcha_id}")
def cryptocrops_telegram_captcha_page(captcha_id: str) -> Response:
    session = cleanup_cryptocrops_captchas().get(str(captcha_id or "")) or {}
    if not session or session.get("status") != "waiting":
        return Response("<h3>Bu CAPTCHA oturumu kapandi.</h3>", status_code=410, media_type="text/html")
    site_key = str(session.get("site_key") or "")
    safe_id = "".join(ch for ch in str(captcha_id) if ch.isalnum() or ch in "-_")
    html = f'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nexus CryptoCrops CAPTCHA</title><script src="https://js.hcaptcha.com/1/api.js" async defer></script><style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#07150d;color:#f4f8ee;font-family:Segoe UI,Arial}}.box{{width:min(92vw,460px);padding:28px;border:1px solid #4e7b5d;border-radius:22px;background:#10291b;text-align:center;box-shadow:0 24px 80px #0008}}h2{{color:#f3d26a}}#status{{color:#b8d4c0;margin:14px 0}}</style></head><body><div class="box"><h2>Nexus CryptoCrops</h2><p id="status">CAPTCHA dogrulamasini tamamla.</p><div class="h-captcha" data-sitekey="{site_key}" data-theme="dark" data-callback="done"></div></div><script>async function done(token){{const s=document.getElementById('status');s.textContent='Dogrulama gonderiliyor...';try{{const r=await fetch('/cryptocrops/api/telegram/captcha/solve',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{captcha_id:'{safe_id}',captcha_token:token}})}});if(!r.ok)throw 0;s.textContent='✅ Tamamlandi. Telegrama veya oyuna donebilirsin.';s.style.color='#76ef9b';}}catch(e){{s.textContent='⚠️ Gonderilemedi, tekrar dene.';s.style.color='#ffb36b';}}}}</script></body></html>'''
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-store"})


def api_auth_for_app(payload: AuthPayload, app_key: str) -> dict[str, Any]:
    ensure_shapes()
    state = app_state(app_key)
    lic = find_license_by_key(payload.license_key, app_key)
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
    if lic.get("tamper_detected"):
        return {"success": False, "error": "Connect Nexus."}
    if not lic.get("active", True):
        return {"success": False, "error": "Lisans pasif"}
    client_error = validate_client_binding(lic, payload.client_id, payload.script_id)
    if client_error:
        return {"success": False, "error": client_error}
    account_error = validate_account_binding(lic, payload.account_id)
    if account_error:
        return {"success": False, "error": account_error}
    token = secrets.token_urlsafe(32)
    lic["session_token"] = token
    lic["online"] = True
    lic["last_seen_at"] = utc_now()
    lic["last_page"] = payload.page or ""
    lic["last_user_agent"] = payload.user_agent or ""
    save_state(force=app_key != FLASH_APP_KEY)
    return {
        "success": True,
        "token": token,
        "license": sanitize_license(lic),
        "settings": state.get("settings", {}),
        "bot": summarize_bot_bundle(app_key),
    }


def api_heartbeat_for_app(payload: HeartbeatPayload, app_key: str) -> dict[str, Any]:
    lic = find_license_by_session(payload.token, app_key)
    if not lic:
        return {"success": False, "error": "Oturum gecersiz"}
    if lic.get("tamper_detected"):
        return {"success": False, "error": "Connect Nexus."}
    binding_error = validate_runtime_binding(lic, payload.client_id, payload.script_id, payload.account_id)
    if binding_error:
        return {"success": False, "error": binding_error}
    lic["online"] = True
    lic["last_seen_at"] = utc_now()
    lic["last_page"] = payload.page or ""
    return {"success": True, "server_time": utc_now(), "settings": app_state(app_key).get("settings", {})}


def api_bot_bundle_for_app(token: str, client_id: str, script_id: str | None, account_id: str | None, app_key: str) -> dict[str, Any]:
    lic = find_license_by_session(token, app_key)
    if not lic:
        return {"success": False, "error": "Oturum gecersiz"}
    if lic.get("tamper_detected"):
        return {"success": False, "error": "Connect Nexus."}
    binding_error = validate_runtime_binding(lic, client_id, script_id, account_id)
    if binding_error:
        return {"success": False, "error": binding_error}
    bundle = app_state(app_key).get("bot_bundle") or {}
    content = str(bundle.get("content") or "")
    if not content:
        return {"success": False, "error": "Bot henuz yuklenmedi"}
    lic["last_seen_at"] = utc_now()
    return {
        "success": True,
        "name": bundle.get("name") or default_bot_name(app_key),
        "version": bundle.get("version") or 0,
        "hash": bundle.get("hash") or "",
        "encoding": "xor-base64",
        "encrypted": encrypt_for_client(content, client_id),
    }


def admin_license_create_for_app(payload: LicenseCreatePayload, x_admin_token: str | None, app_key: str) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    state = app_state(app_key)
    key = (payload.key or "").strip() or generate_license_key(app_key)
    if find_license_by_key(key, app_key):
        return {"success": False, "error": "Bu key zaten var"}
    allowed_client_id = (payload.allowed_client_id or "").strip()
    if allowed_client_id and find_license_by_client_script(allowed_client_id, None, app_key):
        return {"success": False, "error": "Bu script kimligi zaten var"}
    now = utc_now()
    lic = {
        "id": secrets.token_hex(8),
        "name": (payload.name or "User").strip(),
        "key": key,
        "active": bool(payload.active),
        "multi_account": bool(payload.multi_account),
        "account_id": "",
        "client_id": "",
        "script_id": "",
        "allowed_client_id": allowed_client_id,
        "session_token": "",
        "online": False,
        "created_at": now,
        "last_seen_at": "",
        "last_page": "",
        "tamper_detected": False,
        "tamper_reason": "",
        "tamper_at": "",
        "tamper_report": {},
    }
    state["licenses"].insert(0, lic)
    save_state(force=True)
    return {"success": True, "license": sanitize_license(lic)}


def admin_license_toggle_for_app(payload: dict[str, Any], x_admin_token: str | None, app_key: str) -> dict[str, Any]:
    require_admin(x_admin_token)
    lic = find_license_by_id(str(payload.get("license_id") or ""), app_key)
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
    if "active" in payload:
        if bool(payload.get("active")) and lic.get("tamper_detected"):
            return {"success": False, "error": "F12 damgasi temizlenmeden aktif edilemez"}
        lic["active"] = bool(payload.get("active"))
    if "multi_account" in payload:
        lic["multi_account"] = bool(payload.get("multi_account"))
    if payload.get("reset_account"):
        lic["account_id"] = ""
    save_state(force=True)
    return {"success": True, "license": sanitize_license(lic)}


def admin_license_key_for_app(payload: dict[str, Any], x_admin_token: str | None, app_key: str) -> dict[str, Any]:
    require_admin(x_admin_token)
    lic = find_license_by_id(str(payload.get("license_id") or ""), app_key)
    new_key = str(payload.get("key") or "").strip()
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
    if not new_key:
        return {"success": False, "error": "Key bos olamaz"}
    other = find_license_by_key(new_key, app_key)
    if other and other.get("id") != lic.get("id"):
        return {"success": False, "error": "Bu key baska lisansta var"}
    lic["key"] = new_key
    save_state(force=True)
    return {"success": True, "license": sanitize_license(lic)}


def admin_license_delete_for_app(payload: dict[str, Any], x_admin_token: str | None, app_key: str) -> dict[str, Any]:
    require_admin(x_admin_token)
    state = app_state(app_key)
    license_id = str(payload.get("license_id") or "")
    before = len(state.get("licenses") or [])
    state["licenses"] = [x for x in state.get("licenses", []) if x.get("id") != license_id]
    if app_key in (CROPCROPS_APP_KEY, LIGHTNING_APP_KEY):
        packages = state.get("script_packages") or {}
        state["script_packages"] = {key: value for key, value in packages.items() if str(value.get("license_id") or "") != license_id}
        save_script_packages(app_key)
    save_state(force=True)
    return {"success": True, "deleted": before - len(state["licenses"])}


def api_tamper_report_for_app(payload: TamperPayload, app_key: str) -> dict[str, Any]:
    ensure_shapes()
    if app_key == FLASH_APP_KEY and payload.source != "loader_keydown_v2":
        # Legacy loaders mislabeled geometry detections as bot_keydown. They
        # cannot prove a key press and must never permanently disable a license.
        return {"success": True, "ignored": True, "reason": "legacy_unverified_signal", "loader_update_required": True}
    lic = find_license_by_session(payload.token, app_key)
    if not lic:
        lic = find_license_by_key(payload.license_key, app_key)
    if not lic:
        lic = find_license_by_client_script(payload.client_id, payload.script_id, app_key)
    if not lic and app_key != FLASH_APP_KEY:
        lic = find_recent_online_license_for_tamper(payload, app_key)
    if not lic:
        app_state(app_key)["last_tamper_miss"] = {
            "reason": str(payload.reason or "f12")[:80],
            "source": str(payload.source or "client")[:80],
            "license_key_present": bool(str(payload.license_key or "").strip()),
            "client_id": str(payload.client_id or "")[:160],
            "script_id": str(payload.script_id or "")[:160],
            "account_id": str(payload.account_id or "")[:160],
            "page": str(payload.page or "")[:500],
            "user_agent": str(payload.user_agent or "")[:500],
            "reported_at": utc_now(),
        }
        save_state(force=True)
        return {"success": False, "error": "Lisans bulunamadi"}
    now = utc_now()
    report = {
        "reason": str(payload.reason or "f12")[:80],
        "source": str(payload.source or "client")[:80],
        "license_key": str(payload.license_key or "")[:180],
        "client_id": str(payload.client_id or "")[:160],
        "script_id": str(payload.script_id or "")[:160],
        "account_id": str(payload.account_id or "")[:160],
        "page": str(payload.page or "")[:500],
        "user_agent": str(payload.user_agent or "")[:500],
        "reported_at": now,
    }
    if report["client_id"] and not str(lic.get("client_id") or "").strip():
        lic["client_id"] = report["client_id"]
    if report["script_id"] and not str(lic.get("script_id") or "").strip():
        lic["script_id"] = report["script_id"]
    lic["tamper_detected"] = True
    lic["tamper_reason"] = report["reason"]
    lic["tamper_at"] = now
    lic["tamper_report"] = report
    lic["active"] = False
    lic["online"] = False
    lic["session_token"] = ""
    app_state(app_key)["last_tamper_lock"] = {
        "license_id": str(lic.get("id") or ""),
        "name": str(lic.get("name") or ""),
        "reason": report["reason"],
        "source": report["source"],
        "client_id": report["client_id"],
        "script_id": report["script_id"],
        "reported_at": now,
    }
    save_state(force=True)
    return {"success": True, "locked": True}


def find_recent_online_license_for_tamper(payload: TamperPayload, app_key: str) -> dict[str, Any] | None:
    now_ts = datetime.now(timezone.utc).timestamp()
    incoming_account = normalize_account_id(payload.account_id)
    incoming_client = str(payload.client_id or "").strip()
    candidates: list[dict[str, Any]] = []
    for item in app_state(app_key).get("licenses") or []:
        if not isinstance(item, dict):
            continue
        if item.get("tamper_detected") or not item.get("active", True):
            continue
        if incoming_client:
            stored_client = str(item.get("client_id") or "").strip()
            allowed_client = str(item.get("allowed_client_id") or "").strip()
            if incoming_client not in (stored_client, allowed_client):
                continue
        if incoming_account:
            known_accounts = {
                str(item.get("account_id") or "").strip(),
                str(item.get("last_account_id") or "").strip(),
            }
            if any(known_accounts) and incoming_account not in known_accounts:
                continue
        seen = parse_time(item.get("last_seen_at"))
        if item.get("online") and seen and now_ts - seen <= 240:
            candidates.append(item)
    if len(candidates) == 1:
        return candidates[0]
    return None


def admin_license_tamper_clear_for_app(payload: dict[str, Any], x_admin_token: str | None, app_key: str) -> dict[str, Any]:
    require_admin(x_admin_token)
    lic = find_license_by_id(str(payload.get("license_id") or ""), app_key)
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
    lic["tamper_detected"] = False
    lic["tamper_reason"] = ""
    lic["tamper_at"] = ""
    lic["tamper_report"] = {}
    lic["session_token"] = ""
    lic["online"] = False
    save_state(force=True)
    return {"success": True, "license": sanitize_license(lic)}


def admin_bot_upload_for_app(payload: BotUploadPayload, x_admin_token: str | None, app_key: str) -> dict[str, Any]:
    require_admin(x_admin_token)
    state = app_state(app_key)
    content = str(payload.content or "")
    if not content.strip():
        return {"success": False, "error": "Bot icerigi bos"}
    old = state.get("bot_bundle") or {}
    bundle = {
        "name": payload.file_name or default_bot_name(app_key),
        "content": content,
        "hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "version": int(old.get("version") or 0) + 1,
        "updated_at": utc_now(),
    }
    state["bot_bundle"] = bundle
    save_bot_bundle(force=True, app_key=app_key)
    save_state(force=True)
    return {"success": True, "bot": summarize_bot_bundle(app_key)}


def ensure_shapes() -> None:
    RUNTIME_STATE.setdefault("licenses", [])
    RUNTIME_STATE.setdefault("bot_bundle", {"name": "", "content": "", "hash": "", "version": 0, "updated_at": ""})
    RUNTIME_STATE.setdefault("settings", {"heartbeat_seconds": 30, "bind_mode": "first_account"})
    for app_key in (FLASH_APP_KEY, AZTLACOIN_APP_KEY, CROPCROPS_APP_KEY, LIGHTNING_APP_KEY):
        RUNTIME_STATE.setdefault(app_key, {})
        RUNTIME_STATE[app_key].setdefault("licenses", [])
        RUNTIME_STATE[app_key].setdefault("bot_bundle", {"name": "", "content": "", "hash": "", "version": 0, "updated_at": ""})
        RUNTIME_STATE[app_key].setdefault("settings", {"heartbeat_seconds": 30, "bind_mode": "first_account"})
    RUNTIME_STATE[CROPCROPS_APP_KEY].setdefault("script_packages", {})
    RUNTIME_STATE[CROPCROPS_APP_KEY].setdefault("telegram_captchas", {})
    RUNTIME_STATE[LIGHTNING_APP_KEY].setdefault("script_packages", {})
    for state in (RUNTIME_STATE, RUNTIME_STATE[FLASH_APP_KEY], RUNTIME_STATE[AZTLACOIN_APP_KEY], RUNTIME_STATE[CROPCROPS_APP_KEY], RUNTIME_STATE[LIGHTNING_APP_KEY]):
        for lic in state.get("licenses") or []:
            if not isinstance(lic, dict):
                continue
            lic.setdefault("multi_account", False)
            lic.setdefault("account_id", "")
            lic.setdefault("client_id", "")
            lic.setdefault("script_id", "")
            lic.setdefault("allowed_client_id", "")
            lic.setdefault("online", False)
            lic.setdefault("tamper_detected", False)
            lic.setdefault("tamper_reason", "")
            lic.setdefault("tamper_at", "")
            lic.setdefault("tamper_report", {})
            lic.setdefault("telegram_token", "")
            lic.setdefault("telegram_chat_id", "")
            lic.setdefault("telegram_bot_username", "")


def find_license_by_key(key: str | None, app_key: str = "minerbyts") -> dict[str, Any] | None:
    wanted = str(key or "").strip()
    if not wanted:
        return None
    for item in app_state(app_key).get("licenses") or []:
        if isinstance(item, dict) and str(item.get("key") or "").strip() == wanted:
            return item
    return None


def find_license_by_session(token: str | None, app_key: str = "minerbyts") -> dict[str, Any] | None:
    wanted = str(token or "").strip()
    if not wanted:
        return None
    for item in app_state(app_key).get("licenses") or []:
        if isinstance(item, dict) and str(item.get("session_token") or "").strip() == wanted:
            return item
    return None


def find_license_by_id(license_id: str | None, app_key: str = "minerbyts") -> dict[str, Any] | None:
    wanted = str(license_id or "").strip()
    if not wanted:
        return None
    for item in app_state(app_key).get("licenses") or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip() == wanted:
            return item
    return None


def find_license_by_client_script(client_id: str | None, script_id: str | None, app_key: str = "minerbyts") -> dict[str, Any] | None:
    wanted_client = str(client_id or "").strip()
    wanted_script = str(script_id or "").strip()
    if not wanted_client and not wanted_script:
        return None
    for item in app_state(app_key).get("licenses") or []:
        if not isinstance(item, dict):
            continue
        stored_client = str(item.get("client_id") or "").strip()
        allowed_client = str(item.get("allowed_client_id") or "").strip()
        if wanted_client and wanted_client not in (stored_client, allowed_client):
            continue
        if wanted_script and str(item.get("script_id") or "").strip() not in ("", wanted_script):
            continue
        return item
    return None


def validate_client_binding(lic: dict[str, Any], client_id: str | None, script_id: str | None) -> str | None:
    incoming_client = str(client_id or "").strip()
    incoming_script = str(script_id or "").strip()
    if not incoming_client:
        return "Client ID eksik"
    allowed = str(lic.get("allowed_client_id") or "").strip()
    if allowed and incoming_client != allowed:
        return "Bu script bu lisansa ait degil"
    if not lic.get("client_id"):
        lic["client_id"] = incoming_client
    if not lic.get("script_id") and incoming_script:
        lic["script_id"] = incoming_script
    if str(lic.get("client_id") or "") != incoming_client:
        return "Client ID uyusmuyor"
    if str(lic.get("script_id") or "") and incoming_script and str(lic.get("script_id")) != incoming_script:
        return "Script ID uyusmuyor"
    return None


def validate_account_binding(lic: dict[str, Any], account_id: str | None) -> str | None:
    incoming = normalize_account_id(account_id)
    if not incoming:
        return None
    if lic.get("multi_account"):
        lic["last_account_id"] = incoming
        return None
    if not lic.get("account_id"):
        lic["account_id"] = incoming
    elif str(lic.get("account_id") or "") != incoming:
        lic["last_account_id"] = incoming
    return None


def validate_runtime_binding(lic: dict[str, Any], client_id: str | None, script_id: str | None, account_id: str | None) -> str | None:
    return validate_client_binding(lic, client_id, script_id) or validate_account_binding(lic, account_id)


def normalize_account_id(value: str | None) -> str:
    return str(value or "").strip()[:160]


def sanitize_license(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "key": item.get("key", ""),
        "active": item.get("active", True),
        "multi_account": item.get("multi_account", False),
        "account_id": item.get("account_id", ""),
        "last_account_id": item.get("last_account_id", ""),
        "client_id": item.get("client_id", ""),
        "script_id": item.get("script_id", ""),
        "allowed_client_id": item.get("allowed_client_id", ""),
        "online": item.get("online", False),
        "tamper_detected": item.get("tamper_detected", False),
        "tamper_reason": item.get("tamper_reason", ""),
        "tamper_at": item.get("tamper_at", ""),
        "tamper_report": item.get("tamper_report", {}),
        "created_at": item.get("created_at", ""),
        "last_seen_at": item.get("last_seen_at", ""),
        "last_page": item.get("last_page", ""),
    }


def summarize_bot_bundle(app_key: str = "minerbyts") -> dict[str, Any]:
    bundle = app_state(app_key).get("bot_bundle") or {}
    return {
        "name": bundle.get("name", ""),
        "hash": bundle.get("hash", ""),
        "version": bundle.get("version", 0),
        "updated_at": bundle.get("updated_at", ""),
        "uploaded": bool(bundle.get("content")),
    }


def generate_license_key(app_key: str = "minerbyts") -> str:
    prefix = "ZNC" if app_key == FLASH_APP_KEY else ("AZT" if app_key == AZTLACOIN_APP_KEY else ("NXL" if app_key == LIGHTNING_APP_KEY else "MBF"))
    return prefix + "-" + "-".join(secrets.token_hex(2).upper() for _ in range(4))


def default_bot_name(app_key: str = "minerbyts") -> str:
    if app_key == FLASH_APP_KEY:
        return "NECUS-ZUNCIA-BOT-2.txt"
    if app_key == AZTLACOIN_APP_KEY:
        return "botazalt.txt"
    if app_key == LIGHTNING_APP_KEY:
        return "BotLig.txt"
    return "botfree.txt"


def encrypt_for_client(text: str, client_id: str) -> str:
    plain = text.encode("utf-8")
    key = (client_id or config.PROJECT_NAME or "minerbytsfree").encode("utf-8")
    out = bytes([plain[i] ^ key[i % len(key)] for i in range(len(plain))])
    return base64.b64encode(out).decode("ascii")


def require_admin(token: str | None) -> None:
    if not config.ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN missing")
    if token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def build_supabase_client() -> Client | None:
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
        return None
    try:
        return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    except Exception as exc:
        RUNTIME_STATE["storage_error"] = str(exc)
        return None


def load_state() -> None:
    if not SUPABASE:
        return
    try:
        result = SUPABASE.table("app_state").select("value").eq("key", APP_STATE_KEY).limit(1).execute()
        rows = result.data or []
        if rows and isinstance(rows[0].get("value"), dict):
            RUNTIME_STATE.update(rows[0]["value"])
        RUNTIME_STATE.pop("storage_error", None)
    except Exception as exc:
        RUNTIME_STATE["storage_error"] = str(exc)


def load_bot_bundle() -> None:
    if not SUPABASE:
        return
    try:
        result = SUPABASE.table("app_state").select("value").eq("key", BOT_BUNDLE_KEY).limit(1).execute()
        rows = result.data or []
        if rows and isinstance(rows[0].get("value"), dict):
            RUNTIME_STATE["bot_bundle"] = rows[0]["value"]
        result = SUPABASE.table("app_state").select("value").eq("key", FLASH_BOT_BUNDLE_KEY).limit(1).execute()
        rows = result.data or []
        if rows and isinstance(rows[0].get("value"), dict):
            RUNTIME_STATE[FLASH_APP_KEY]["bot_bundle"] = rows[0]["value"]
        result = SUPABASE.table("app_state").select("value").eq("key", AZTLACOIN_BOT_BUNDLE_KEY).limit(1).execute()
        rows = result.data or []
        if rows and isinstance(rows[0].get("value"), dict):
            RUNTIME_STATE[AZTLACOIN_APP_KEY]["bot_bundle"] = rows[0]["value"]
        result = SUPABASE.table("app_state").select("value").eq("key", CROPCROPS_BOT_BUNDLE_KEY).limit(1).execute()
        rows = result.data or []
        if rows and isinstance(rows[0].get("value"), dict):
            RUNTIME_STATE[CROPCROPS_APP_KEY]["bot_bundle"] = rows[0]["value"]
        result = SUPABASE.table("app_state").select("value").eq("key", LIGHTNING_BOT_BUNDLE_KEY).limit(1).execute()
        rows = result.data or []
        if rows and isinstance(rows[0].get("value"), dict):
            RUNTIME_STATE[LIGHTNING_APP_KEY]["bot_bundle"] = rows[0]["value"]
        RUNTIME_STATE.pop("bot_storage_error", None)
    except Exception as exc:
        RUNTIME_STATE["bot_storage_error"] = str(exc)


def load_script_packages() -> None:
    """Load large userscript packages separately from frequently saved runtime state."""
    if not SUPABASE:
        return
    for app_key, storage_key in (
        (CROPCROPS_APP_KEY, CROPCROPS_SCRIPT_PACKAGES_KEY),
        (LIGHTNING_APP_KEY, LIGHTNING_SCRIPT_PACKAGES_KEY),
    ):
        legacy_packages = app_state(app_key).get("script_packages") or {}
        try:
            result = SUPABASE.table("app_state").select("value").eq("key", storage_key).limit(1).execute()
            rows = result.data or []
            stored = rows[0].get("value") if rows else None
            if isinstance(stored, dict):
                app_state(app_key)["script_packages"] = stored
            elif legacy_packages:
                # One-time migration from the old runtime-state row. Future heartbeat
                # saves never upload these multi-megabyte packages again.
                save_app_state(storage_key, legacy_packages, f"{app_key}_script_storage_error")
        except Exception as exc:
            RUNTIME_STATE[f"{app_key}_script_storage_error"] = str(exc)


def save_state(force: bool = False) -> None:
    global LAST_SYNC_EPOCH
    if not SUPABASE:
        return
    now = time.monotonic()
    if not force and LAST_SYNC_EPOCH and now - LAST_SYNC_EPOCH < max(10, config.STATE_SYNC_MIN_SECONDS):
        return
    LAST_SYNC_EPOCH = now
    payload = dict(RUNTIME_STATE)
    bot = dict(payload.get("bot_bundle") or {})
    bot.pop("content", None)
    payload["bot_bundle"] = bot
    flash_state = dict(payload.get(FLASH_APP_KEY) or {})
    flash_bot = dict(flash_state.get("bot_bundle") or {})
    flash_bot.pop("content", None)
    flash_state["bot_bundle"] = flash_bot
    payload[FLASH_APP_KEY] = flash_state
    aztlacoin_state = dict(payload.get(AZTLACOIN_APP_KEY) or {})
    aztlacoin_bot = dict(aztlacoin_state.get("bot_bundle") or {})
    aztlacoin_bot.pop("content", None)
    aztlacoin_state["bot_bundle"] = aztlacoin_bot
    payload[AZTLACOIN_APP_KEY] = aztlacoin_state
    cryptocrops_state = dict(payload.get(CROPCROPS_APP_KEY) or {})
    cryptocrops_bot = dict(cryptocrops_state.get("bot_bundle") or {})
    cryptocrops_bot.pop("content", None)
    cryptocrops_state["bot_bundle"] = cryptocrops_bot
    cryptocrops_state.pop("script_packages", None)
    payload[CROPCROPS_APP_KEY] = cryptocrops_state
    lightning_state = dict(payload.get(LIGHTNING_APP_KEY) or {})
    lightning_bot = dict(lightning_state.get("bot_bundle") or {})
    lightning_bot.pop("content", None)
    lightning_state["bot_bundle"] = lightning_bot
    lightning_state.pop("script_packages", None)
    payload[LIGHTNING_APP_KEY] = lightning_state
    save_app_state(APP_STATE_KEY, payload, "storage_error")


def save_bot_bundle(force: bool = False, app_key: str = "minerbyts") -> None:
    if not SUPABASE:
        return
    if app_key == FLASH_APP_KEY:
        save_app_state(FLASH_BOT_BUNDLE_KEY, RUNTIME_STATE[FLASH_APP_KEY].get("bot_bundle") or {}, "flash_bot_storage_error")
    elif app_key == AZTLACOIN_APP_KEY:
        save_app_state(AZTLACOIN_BOT_BUNDLE_KEY, RUNTIME_STATE[AZTLACOIN_APP_KEY].get("bot_bundle") or {}, "aztlacoin_bot_storage_error")
    elif app_key == CROPCROPS_APP_KEY:
        save_app_state(CROPCROPS_BOT_BUNDLE_KEY, RUNTIME_STATE[CROPCROPS_APP_KEY].get("bot_bundle") or {}, "cryptocrops_bot_storage_error")
    elif app_key == LIGHTNING_APP_KEY:
        save_app_state(LIGHTNING_BOT_BUNDLE_KEY, RUNTIME_STATE[LIGHTNING_APP_KEY].get("bot_bundle") or {}, "lightning_bot_storage_error")
    else:
        save_app_state(BOT_BUNDLE_KEY, RUNTIME_STATE.get("bot_bundle") or {}, "bot_storage_error")


def save_script_packages(app_key: str) -> None:
    if not SUPABASE or app_key not in (CROPCROPS_APP_KEY, LIGHTNING_APP_KEY):
        return
    storage_key = CROPCROPS_SCRIPT_PACKAGES_KEY if app_key == CROPCROPS_APP_KEY else LIGHTNING_SCRIPT_PACKAGES_KEY
    packages = app_state(app_key).get("script_packages") or {}
    save_app_state(storage_key, packages, f"{app_key}_script_storage_error")


def save_app_state(key: str, value: dict[str, Any], error_key: str) -> None:
    if not SUPABASE:
        return
    try:
        SUPABASE.table("app_state").upsert({"key": key, "value": value, "updated_at": utc_now()}).execute()
        RUNTIME_STATE["last_sync"] = utc_now()
        RUNTIME_STATE.pop(error_key, None)
    except Exception as exc:
        RUNTIME_STATE[error_key] = str(exc)


def mark_stale_offline() -> None:
    now = time.time()
    changed = False
    for state in (RUNTIME_STATE, RUNTIME_STATE.get(FLASH_APP_KEY) or {}, RUNTIME_STATE.get(AZTLACOIN_APP_KEY) or {}, RUNTIME_STATE.get(CROPCROPS_APP_KEY) or {}, RUNTIME_STATE.get(LIGHTNING_APP_KEY) or {}):
        for lic in state.get("licenses") or []:
            seen = parse_time(lic.get("last_seen_at"))
            if lic.get("online") and seen and now - seen > 120:
                lic["online"] = False
                changed = True
    if changed:
        save_state(force=False)


def parse_time(value: str | None) -> float | None:
    try:
        if not value:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=config.HOST, port=config.PORT, reload=False)
