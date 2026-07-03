from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import Client, create_client

import config


APP_STATE_KEY = "minerbytsfree_runtime"
BOT_BUNDLE_KEY = "minerbytsfree_bot_bundle"
FLASH_BOT_BUNDLE_KEY = "flashminers_bot_bundle"
FLASH_APP_KEY = "flashminers"

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


@app.on_event("startup")
def startup_event() -> None:
    global SUPABASE
    RUNTIME_STATE["status"] = "ready"
    RUNTIME_STATE["started_at"] = utc_now()
    SUPABASE = build_supabase_client()
    load_state()
    load_bot_bundle()
    ensure_shapes()


def app_state(app_key: str = "minerbyts") -> dict[str, Any]:
    ensure_shapes()
    if app_key == FLASH_APP_KEY:
        return RUNTIME_STATE[FLASH_APP_KEY]
    return RUNTIME_STATE


def app_label(app_key: str = "minerbyts") -> str:
    return "flashminers" if app_key == FLASH_APP_KEY else "minerbyts"


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
    binding_error = validate_runtime_binding(lic, payload.client_id, payload.script_id, payload.account_id)
    if binding_error:
        return {"success": False, "error": binding_error}
    lic["online"] = True
    lic["last_seen_at"] = utc_now()
    lic["last_page"] = payload.page or ""
    save_state(force=False)
    return {"success": True, "server_time": utc_now(), "settings": RUNTIME_STATE.get("settings", {})}


@app.get("/api/bot/bundle")
def api_bot_bundle(token: str, client_id: str, script_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
    lic = find_license_by_session(token)
    if not lic:
        return {"success": False, "error": "Oturum gecersiz"}
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


@app.get("/flash/health")
def flash_health() -> dict[str, Any]:
    ensure_shapes()
    state = app_state(FLASH_APP_KEY)
    bundle = state.get("bot_bundle") or {}
    return {
        "success": True,
        "project": "flashminers",
        "status": RUNTIME_STATE.get("status", "unknown"),
        "time": utc_now(),
        "supabase": bool(SUPABASE),
        "license_count": len(state.get("licenses") or []),
        "bot_uploaded": bool(bundle.get("content")),
        "bot_hash": bundle.get("hash", ""),
        "last_sync": RUNTIME_STATE.get("last_sync", ""),
        "storage_error": RUNTIME_STATE.get("storage_error", ""),
    }


@app.post("/flash/api/auth")
def flash_api_auth(payload: AuthPayload) -> dict[str, Any]:
    return api_auth_for_app(payload, FLASH_APP_KEY)


@app.post("/flash/api/heartbeat")
def flash_api_heartbeat(payload: HeartbeatPayload) -> dict[str, Any]:
    return api_heartbeat_for_app(payload, FLASH_APP_KEY)


@app.get("/flash/api/bot/bundle")
def flash_api_bot_bundle(token: str, client_id: str, script_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
    return api_bot_bundle_for_app(token, client_id, script_id, account_id, FLASH_APP_KEY)


@app.get("/flash/admin/state")
def flash_admin_state(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    return {"success": True, "state": app_state(FLASH_APP_KEY)}


@app.get("/flash/admin/licenses")
def flash_admin_licenses(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    ensure_shapes()
    mark_stale_offline()
    return {"success": True, "licenses": [sanitize_license(x) for x in app_state(FLASH_APP_KEY).get("licenses", [])]}


@app.post("/flash/admin/license/create")
def flash_admin_license_create(payload: LicenseCreatePayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_create_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.post("/flash/admin/license/toggle")
def flash_admin_license_toggle(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_toggle_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.post("/flash/admin/license/key")
def flash_admin_license_key(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_key_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.post("/flash/admin/license/delete")
def flash_admin_license_delete(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_license_delete_for_app(payload, x_admin_token, FLASH_APP_KEY)


@app.post("/flash/admin/bot/upload")
def flash_admin_bot_upload(payload: BotUploadPayload, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    return admin_bot_upload_for_app(payload, x_admin_token, FLASH_APP_KEY)


def api_auth_for_app(payload: AuthPayload, app_key: str) -> dict[str, Any]:
    ensure_shapes()
    state = app_state(app_key)
    lic = find_license_by_key(payload.license_key, app_key)
    if not lic:
        return {"success": False, "error": "Lisans bulunamadi"}
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
        "settings": state.get("settings", {}),
        "bot": summarize_bot_bundle(app_key),
    }


def api_heartbeat_for_app(payload: HeartbeatPayload, app_key: str) -> dict[str, Any]:
    lic = find_license_by_session(payload.token, app_key)
    if not lic:
        return {"success": False, "error": "Oturum gecersiz"}
    binding_error = validate_runtime_binding(lic, payload.client_id, payload.script_id, payload.account_id)
    if binding_error:
        return {"success": False, "error": binding_error}
    lic["online"] = True
    lic["last_seen_at"] = utc_now()
    lic["last_page"] = payload.page or ""
    save_state(force=False)
    return {"success": True, "server_time": utc_now(), "settings": app_state(app_key).get("settings", {})}


def api_bot_bundle_for_app(token: str, client_id: str, script_id: str | None, account_id: str | None, app_key: str) -> dict[str, Any]:
    lic = find_license_by_session(token, app_key)
    if not lic:
        return {"success": False, "error": "Oturum gecersiz"}
    binding_error = validate_runtime_binding(lic, client_id, script_id, account_id)
    if binding_error:
        return {"success": False, "error": binding_error}
    bundle = app_state(app_key).get("bot_bundle") or {}
    content = str(bundle.get("content") or "")
    if not content:
        return {"success": False, "error": "Bot henuz yuklenmedi"}
    lic["last_seen_at"] = utc_now()
    save_state(force=False)
    return {
        "success": True,
        "name": bundle.get("name") or ("BOT2.txt" if app_key == FLASH_APP_KEY else "botfree.txt"),
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
    save_state(force=True)
    return {"success": True, "deleted": before - len(state["licenses"])}


def admin_bot_upload_for_app(payload: BotUploadPayload, x_admin_token: str | None, app_key: str) -> dict[str, Any]:
    require_admin(x_admin_token)
    state = app_state(app_key)
    content = str(payload.content or "")
    if not content.strip():
        return {"success": False, "error": "Bot icerigi bos"}
    old = state.get("bot_bundle") or {}
    bundle = {
        "name": payload.file_name or ("BOT2.txt" if app_key == FLASH_APP_KEY else "botfree.txt"),
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
    RUNTIME_STATE.setdefault(FLASH_APP_KEY, {})
    RUNTIME_STATE[FLASH_APP_KEY].setdefault("licenses", [])
    RUNTIME_STATE[FLASH_APP_KEY].setdefault("bot_bundle", {"name": "", "content": "", "hash": "", "version": 0, "updated_at": ""})
    RUNTIME_STATE[FLASH_APP_KEY].setdefault("settings", {"heartbeat_seconds": 30, "bind_mode": "first_account"})
    for state in (RUNTIME_STATE, RUNTIME_STATE[FLASH_APP_KEY]):
        for lic in state.get("licenses") or []:
            if not isinstance(lic, dict):
                continue
            lic.setdefault("multi_account", False)
            lic.setdefault("account_id", "")
            lic.setdefault("client_id", "")
            lic.setdefault("script_id", "")
            lic.setdefault("allowed_client_id", "")
            lic.setdefault("online", False)


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
    if str(lic.get("account_id") or "") != incoming:
        return "Bu key baska hesaba bagli"
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
    prefix = "FMF" if app_key == FLASH_APP_KEY else "MBF"
    return prefix + "-" + "-".join(secrets.token_hex(2).upper() for _ in range(4))


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
        RUNTIME_STATE.pop("bot_storage_error", None)
    except Exception as exc:
        RUNTIME_STATE["bot_storage_error"] = str(exc)


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
    save_app_state(APP_STATE_KEY, payload, "storage_error")


def save_bot_bundle(force: bool = False, app_key: str = "minerbyts") -> None:
    if not SUPABASE:
        return
    if app_key == FLASH_APP_KEY:
        save_app_state(FLASH_BOT_BUNDLE_KEY, RUNTIME_STATE[FLASH_APP_KEY].get("bot_bundle") or {}, "flash_bot_storage_error")
    else:
        save_app_state(BOT_BUNDLE_KEY, RUNTIME_STATE.get("bot_bundle") or {}, "bot_storage_error")


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
    for state in (RUNTIME_STATE, RUNTIME_STATE.get(FLASH_APP_KEY) or {}):
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
