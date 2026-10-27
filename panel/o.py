#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import re
import secrets
import subprocess
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
SETTINGS_FILE = BASE_DIR / "cryptocrops_ultra_panel_settings.json"
BOT_FILE = ROOT_DIR / ".codex" / "yenı data.txt"
GENERATED_DIR = BASE_DIR / "generated_cryptocrops_ultra_scripts"
GENERATED_DIR.mkdir(exist_ok=True)
SCRIPT_INDEX_FILE = BASE_DIR / "generated_cryptocrops_ultra_scripts_index.json"

DEFAULT_SETTINGS = {
    "server_url": "https://nexus-active-passive.yakuptoraman588.workers.dev",
    "admin_token": "MbfAdmin_18free!7429",
    "selected_bot_path": str(BOT_FILE),
}

CLIENT_TEMPLATE = r'''// ==UserScript==
// @name         __CLIENT_NAME__
// @namespace    nexus.cryptocrops.ultra
// @version      1.0.__SCRIPT_BUILD__
// @description  Nexus CryptoCrops Ultra secure loader
// @match        https://cryptocrops.net/*
// @downloadURL  __SERVER_URL__/cryptocrops/script/__SCRIPT_ID__.user.js?client_id=__CLIENT_ID__
// @updateURL    __SERVER_URL__/cryptocrops/script/__SCRIPT_ID__.user.js?client_id=__CLIENT_ID__
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      __SERVER_HOST__
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    const SERVER_URL = '__SERVER_URL__';
    const CLIENT_NAME = '__CLIENT_NAME__';
    const CLIENT_ID = '__CLIENT_ID__';
    const SCRIPT_ID = '__SCRIPT_ID__';
    const API_PREFIX = '/cryptocrops';
    const STORAGE_KEY = 'cryptocrops_ultra_auth_' + CLIENT_ID;
    const GLOBAL_STORAGE_KEY = 'cryptocrops_ultra_auth_latest';
    // Session token is deliberately short-lived; this key is per generated
    // script and survives token renewal, page reloads, and server restarts.
    const LICENSE_KEY_STORAGE = 'cryptocrops_ultra_license_key_' + CLIENT_ID;
    const TELEGRAM_URL = '';
    const TELEGRAM_ICON = '';
    let sessionToken = '';
    let loadedBotHash = '';
    let authenticatedBot = null;
    let heartbeatTimer = null;
    let uiRoot = null;
    let reauthInProgress = false;
    let silentRetryTimer = null;
    let banRequestSent = false;
    let releaseEmbeddedBot = null;
    globalThis.__NEXUS_CROPCROPS_ULTRA_START__ = new Promise((resolve) => { releaseEmbeddedBot = resolve; });

    function gmRequest(method, url, body, attempt = 0) {
        return new Promise((resolve) => {
            GM_xmlhttpRequest({
                method,
                url,
                timeout: 45000,
                headers: { 'Content-Type': 'application/json' },
                data: body ? JSON.stringify(body) : undefined,
                onload: (res) => {
                    try {
                        const parsed = JSON.parse(res.responseText || '{}');
                        if (res.status >= 400 && parsed && !parsed.error) parsed.error = 'HTTP ' + res.status;
                        resolve(parsed);
                    } catch(e) {
                        resolve({ success:false, error:'Bad server response', status:res.status || 0 });
                    }
                },
                onerror: () => {
                    if (attempt < 2) return setTimeout(() => gmRequest(method, url, body, attempt + 1).then(resolve), 1800);
                    resolve({ success:false, error:'Connection error' });
                },
                ontimeout: () => {
                    if (attempt < 2) return setTimeout(() => gmRequest(method, url, body, attempt + 1).then(resolve), 1800);
                    resolve({ success:false, error:'Request timeout' });
                }
            });
        });
    }

    function gmGet(url, attempt = 0) {
        return new Promise((resolve) => {
            GM_xmlhttpRequest({
                method: 'GET',
                url,
                timeout: 45000,
                onload: (res) => {
                    try { resolve(JSON.parse(res.responseText || '{}')); }
                    catch(e) { resolve({ success:false, error:'Bad server response' }); }
                },
                onerror: () => {
                    if (attempt < 2) return setTimeout(() => gmGet(url, attempt + 1).then(resolve), 1800);
                    resolve({ success:false, error:'Connection error' });
                },
                ontimeout: () => {
                    if (attempt < 2) return setTimeout(() => gmGet(url, attempt + 1).then(resolve), 1800);
                    resolve({ success:false, error:'Request timeout' });
                }
            });
        });
    }

    function apiUrl(path) {
        return String(SERVER_URL || '').replace(/\/$/, '') + path;
    }

    function saveAuth(payload) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(payload || {})); } catch(e) {}
        try { localStorage.setItem(GLOBAL_STORAGE_KEY, JSON.stringify(payload || {})); } catch(e) {}
        try { GM_setValue(STORAGE_KEY, JSON.stringify(payload || {})); } catch(e) {}
        try { GM_setValue(GLOBAL_STORAGE_KEY, JSON.stringify(payload || {})); } catch(e) {}
        const licenseKey = String((payload || {}).license_key || '').trim();
        // Never erase this fallback on a transient session error. A disabled
        // license is still refused by the server on the next silent check.
        if (licenseKey) {
            try { localStorage.setItem(LICENSE_KEY_STORAGE, licenseKey); } catch(e) {}
            try { GM_setValue(LICENSE_KEY_STORAGE, licenseKey); } catch(e) {}
        }
    }

    function loadAuth() {
        const candidates = [];
        try { candidates.push(localStorage.getItem(STORAGE_KEY)); } catch(e) {}
        try { candidates.push(localStorage.getItem(GLOBAL_STORAGE_KEY)); } catch(e) {}
        try { candidates.push(GM_getValue(STORAGE_KEY)); } catch(e) {}
        try { candidates.push(GM_getValue(GLOBAL_STORAGE_KEY)); } catch(e) {}
        for (const raw of candidates) {
            try {
                if (!raw) continue;
                const parsed = JSON.parse(raw);
                if (parsed && typeof parsed === 'object') return parsed;
            } catch(e) {}
        }
        return {};
    }

    function isTransientError(error) {
        return /connection|timeout|network|bad server response/i.test(String(error || ''));
    }

    function scheduleSilentUnlock(key, delay = 10000) {
        key = String(key || '').trim();
        if (!key) return;
        if (silentRetryTimer) clearTimeout(silentRetryTimer);
        silentRetryTimer = setTimeout(() => {
            silentRetryTimer = null;
            unlockWithKey(key, true);
        }, delay);
    }

    function collectAccountId() {
        try {
            let fp = localStorage.getItem('cryptocrops_ultra_device_id') || '';
            if (!fp) {
                fp = 'dev_' + Math.random().toString(16).slice(2) + Date.now().toString(16);
                localStorage.setItem('cryptocrops_ultra_device_id', fp);
            }
            return fp;
        } catch(e) {
            return CLIENT_ID;
        }
    }

    function getSavedLicenseKey() {
        const current = String((loadAuth() || {}).license_key || '').trim();
        if (current) return current;
        try {
            const saved = String(GM_getValue(LICENSE_KEY_STORAGE) || '').trim();
            if (saved) return saved;
        } catch(e) {}
        try { return String(localStorage.getItem(LICENSE_KEY_STORAGE) || '').trim(); } catch(e) {}
        return '';
    }

    function showGate(message = '') {
        try {
            removeGate();
            const saved = getSavedLicenseKey();
            const text = {
                access:'🌾 NEXUS PRIVATE FARM ACCESS', key:'FARM LICENSE KEY', placeholder:'Enter your farm license key', start:'🌱 START FARM', hint:'Enter your key to access the private farm.', missing:'A farm license key is required.', success:'Access granted. Preparing your farm...'
            };
            uiRoot = document.createElement('div');
            uiRoot.id = 'nexusFreeGate';
            uiRoot.innerHTML = `
                <style>
                    #nexusFreeGate { position:fixed; inset:0; z-index:2147483647; display:grid; place-items:center; font-family:Inter,Segoe UI,Arial,sans-serif; color:#fff8dc; background:radial-gradient(circle at 50% 8%, rgba(244,190,62,.20), transparent 30%), radial-gradient(circle at 12% 88%, rgba(69,131,66,.36), transparent 38%), linear-gradient(180deg, rgba(8,24,12,.90), rgba(3,10,5,.99)); backdrop-filter:blur(16px); }
                    .nfg-card { width:min(430px, calc(100vw - 32px)); border:1px solid rgba(245,200,76,.48); background:linear-gradient(155deg, rgba(38,74,35,.96), rgba(12,30,15,.98)); box-shadow:0 28px 90px rgba(0,0,0,.62), 0 0 55px rgba(115,174,74,.22), inset 0 1px 0 rgba(255,255,255,.08); border-radius:24px; padding:28px; position:relative; overflow:hidden; animation:nfgIn .65s cubic-bezier(.2,.9,.2,1) both; }
                    .nfg-card:has(.nfg-farm-row) { background-image:linear-gradient(155deg, rgba(38,74,35,.96), rgba(12,30,15,.98)), repeating-linear-gradient(135deg, transparent 0 18px, rgba(185,218,109,.035) 18px 20px); }
                    .nfg-card:before { content:""; position:absolute; inset:-2px; background:linear-gradient(115deg, transparent, rgba(250,204,21,.23), transparent); transform:translateX(-120%); animation:nfgSweep 2.8s ease-in-out infinite; }
                    .nfg-card:after { content:""; position:absolute; inset:1px; border-radius:22px; pointer-events:none; border:1px solid rgba(255,255,255,.04); }
                    .nfg-top { position:relative; display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:18px; }
                    .nfg-brand { display:grid; gap:4px; }
                    .nfg-title { font-size:28px; line-height:1; font-weight:950; letter-spacing:.4px; color:#facc15; text-shadow:0 0 24px rgba(250,204,21,.32); }
                    .nfg-sub { color:#b9da8f; font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:2.5px; }
                    .nfg-tg { width:46px; height:46px; border-radius:50%; display:grid; place-items:center; background:rgba(64,111,47,.55); border:1px solid rgba(250,204,21,.36); cursor:default; box-shadow:0 0 28px rgba(110,168,67,.30); position:relative; padding:0; font-size:23px; }
                    .nfg-tg img { width:32px; height:32px; display:block; }
                    .nfg-label { position:relative; color:#f4cf63; font-size:12px; font-weight:900; margin:16px 0 8px; letter-spacing:.6px; }
                    .nfg-input { position:relative; width:100%; box-sizing:border-box; border:1px solid rgba(191,220,124,.32); background:rgba(4,19,7,.76); color:#fff8dc; border-radius:14px; padding:14px 15px; outline:none; font-size:14px; font-weight:900; letter-spacing:.5px; }
                    .nfg-input::placeholder { color:rgba(250,204,21,.42); }
                    .nfg-input:focus { border-color:#facc15; box-shadow:0 0 0 4px rgba(250,204,21,.12); }
                    .nfg-btn { position:relative; width:100%; margin-top:14px; border:0; border-radius:14px; padding:14px; color:#10230e; font-weight:950; letter-spacing:1.4px; background:linear-gradient(135deg,#b7d866,#6fa547,#e4be55); cursor:pointer; box-shadow:0 18px 40px rgba(107,163,70,.30); }
                    .nfg-btn:hover { filter:brightness(1.12); transform:translateY(-1px); }
                    .nfg-status { position:relative; min-height:18px; color:#facc15; font-size:12px; font-weight:900; margin-top:12px; text-align:center; }
                    .nfg-loader { display:none; position:relative; width:54px; height:54px; margin:18px auto 2px; border-radius:50%; border:4px solid rgba(250,204,21,.18); border-top-color:#facc15; animation:nfgSpin .8s linear infinite; }
                    .nfg-loading .nfg-loader { display:block; }
                    .nfg-loading .nfg-btn, .nfg-loading .nfg-input { opacity:.52; pointer-events:none; }
                    .nfg-burst { position:absolute; inset:50%; width:12px; height:12px; border-radius:50%; background:#facc15; transform:translate(-50%,-50%) scale(0); pointer-events:none; }
                    .nfg-success .nfg-burst { animation:nfgBurst .75s ease-out forwards; }
                    .nfg-mini { position:relative; margin-top:10px; color:rgba(255,248,220,.48); text-align:center; font-size:11px; font-weight:800; }
                    .nfg-farm-row { position:relative; display:flex; gap:7px; justify-content:center; margin:16px 0 2px; }
                    .nfg-farm-row i { display:block; width:28px; height:5px; border-radius:10px; background:linear-gradient(90deg,#4e7e35,#9fbe52); box-shadow:0 0 10px rgba(159,190,82,.3); }
                    .nfg-badges { position:relative; display:flex; justify-content:center; gap:8px; margin-top:10px; }
                    .nfg-badge { border:1px solid rgba(185,218,109,.22); background:rgba(10,35,14,.52); border-radius:999px; padding:5px 9px; color:#cfe8ad; font-size:9px; font-weight:900; letter-spacing:.75px; }
                    @keyframes nfgIn { from { opacity:0; transform:translateY(18px) scale(.94); filter:blur(8px); } to { opacity:1; transform:none; filter:none; } }
                    @keyframes nfgSweep { 45%,100% { transform:translateX(120%); } }
                    @keyframes nfgSpin { to { transform:rotate(360deg); } }
                    @keyframes nfgBurst { 0% { transform:translate(-50%,-50%) scale(0); opacity:.95; } 60% { transform:translate(-50%,-50%) scale(75); opacity:.55; } 100% { transform:translate(-50%,-50%) scale(95); opacity:0; } }
                </style>
                <div class="nfg-card">
                    <div class="nfg-burst"></div>
                    <div class="nfg-top">
                        <div class="nfg-brand">
                            <div class="nfg-sub">${text.access}</div>
                            <div class="nfg-title">CryptoCrops Ultra</div>
                        </div>
                        <button class="nfg-tg" id="nfgTelegram" title="Farm access">🚜</button>
                    </div>
                    <label class="nfg-label" for="nfgKey">${text.key}</label>
                    <input class="nfg-input" id="nfgKey" placeholder="${text.placeholder}" value="${escapeAttr(saved)}" autocomplete="off">
                    <button class="nfg-btn" id="nfgUnlock">${text.start}</button>
                    <div class="nfg-loader"></div>
                    <div class="nfg-status" id="nfgStatus">${escapeHtml(message || text.hint)}</div>
                    <div class="nfg-farm-row"><i></i><i></i><i></i><i></i><i></i></div>
                    <div class="nfg-badges"><span class="nfg-badge">LICENSED</span><span class="nfg-badge">FARM SECURED</span><span class="nfg-badge">ULTRA</span></div>
                    <div class="nfg-mini">NEXUS · CROPCROPS · ULTRA</div>
                </div>
            `;
            document.documentElement.appendChild(uiRoot);
            document.getElementById('nfgTelegram').onclick = () => {};
            document.getElementById('nfgUnlock').onclick = async () => {
                const key = String(document.getElementById('nfgKey').value || '').trim();
                if (!key) {
                    setGateStatus(text.missing, true);
                    return;
                }
                await unlockWithKey(key);
            };
            document.getElementById('nfgKey').addEventListener('keydown', (event) => {
                if (event.key === 'Enter') document.getElementById('nfgUnlock').click();
            });
        } catch(e) {}
    }

    function setGateLoading(active, text) {
        if (!uiRoot) return;
        const card = uiRoot.querySelector('.nfg-card');
        if (card) card.classList.toggle('nfg-loading', !!active);
        setGateStatus(text || '', false);
    }

    function setGateStatus(text, bad = false) {
        const status = document.getElementById('nfgStatus');
        if (!status) return;
        status.textContent = text || '';
        status.style.color = bad ? '#fb8c7c' : '#c9e8a2';
    }

    function showGateSuccess() {
        return new Promise((resolve) => {
            if (!uiRoot) return resolve();
            const card = uiRoot.querySelector('.nfg-card');
            if (card) card.classList.add('nfg-success');
            setGateStatus('Access granted. Preparing your farm...', false);
            setTimeout(resolve, 720);
        });
    }

    function removeGate() {
        try {
            const old = document.getElementById('nexusFreeGate');
            if (old) old.remove();
        } catch(e) {}
        uiRoot = null;
    }

    function injectTelegramButton() {
        const apply = () => {
            try {
                if (document.getElementById('nexusBotTelegramBtn')) return true;
                const settingsBtn = document.getElementById('mbSettingsBtn');
                if (!settingsBtn || !settingsBtn.parentElement) return false;
                const btn = document.createElement('button');
                btn.id = 'nexusBotTelegramBtn';
                btn.className = settingsBtn.className || 'mb-icon-btn';
                btn.title = 'Telegram';
                btn.style.cssText = 'width:22px;height:22px;display:inline-grid;place-items:center;background:transparent;border:0;cursor:pointer;padding:0;margin-right:3px;vertical-align:middle;';
                btn.innerHTML = '<img src="' + TELEGRAM_ICON + '" alt="" style="width:19px;height:19px;display:block;border-radius:4px;">';
                btn.onclick = (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    window.open(TELEGRAM_URL, '_blank', 'noopener,noreferrer');
                };
                settingsBtn.parentElement.insertBefore(btn, settingsBtn);
                return true;
            } catch(e) {
                return false;
            }
        };
        if (apply()) return;
        let tries = 0;
        const timer = setInterval(() => {
            tries++;
            if (apply() || tries > 30) clearInterval(timer);
        }, 500);
    }

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }

    function escapeAttr(value) {
        return escapeHtml(value).replace(/`/g, '&#96;');
    }

    function base64ToBytes(b64) {
        const bin = atob(String(b64 || ''));
        const arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        return arr;
    }

    function decryptBot(encrypted) {
        const src = base64ToBytes(encrypted);
        const key = new TextEncoder().encode(CLIENT_ID);
        const out = new Uint8Array(src.length);
        for (let i = 0; i < src.length; i++) out[i] = src[i] ^ key[i % key.length];
        return new TextDecoder().decode(out);
    }

    async function authenticate(licenseKey) {
        licenseKey = String(licenseKey || '').trim();
        if (!licenseKey) return { success:false, error:'License key is required' };
        const accountId = collectAccountId();
        const res = await gmRequest('POST', apiUrl(API_PREFIX + '/api/auth'), {
            license_key: licenseKey,
            client_id: CLIENT_ID,
            script_id: SCRIPT_ID,
            account_id: accountId,
            page: location.href,
            user_agent: navigator.userAgent
        });
        if (res && res.success) {
            sessionToken = res.token || '';
            authenticatedBot = res.bot || null;
            saveAuth({ license_key: licenseKey, session_token: sessionToken, account_id: accountId });
        }
        return res;
    }

    async function heartbeat() {
        if (!sessionToken) return;
        const res = await gmRequest('POST', apiUrl(API_PREFIX + '/api/heartbeat'), {
            token: sessionToken,
            client_id: CLIENT_ID,
            script_id: SCRIPT_ID,
            account_id: collectAccountId(),
            page: location.href
        });
        if (!res || !res.success) {
            sessionToken = '';
            if (heartbeatTimer) clearInterval(heartbeatTimer);
            const savedKey = getSavedLicenseKey();
            if (savedKey && !reauthInProgress) {
                reauthInProgress = true;
                try { await unlockWithKey(savedKey, true); }
                finally { reauthInProgress = false; }
                return;
            }
            showGate((res && res.error) || 'Session expired. Please unlock again.');
        }
    }

    async function fetchAndRunBot() {
        // CryptoCrops botu uretilen userscript'in icine gomuludur. Lisans
        // cevabinda hash zaten geliyor; sayfa/CAPTCHA yenilemelerinde buyuk bot
        // paketini tekrar indirmek gereksiz bant genisligi harciyordu.
        loadedBotHash = (authenticatedBot && authenticatedBot.hash)
            || loadedBotHash
            || ('embedded:' + SCRIPT_ID);
        window.__MINERBYTSFREE_CLIENT__ = {
            serverUrl: SERVER_URL,
            clientId: CLIENT_ID,
            scriptId: SCRIPT_ID,
            sessionToken,
            accountId: collectAccountId(),
            botHash: loadedBotHash
        };
        // Bot, script üretilirken bu loader'ın altına eklenir. CSP nedeniyle
        // sunucudan gelen metni eval etmek yerine kendi Tampermonkey alanında çalışır.
    }

    async function unlockWithKey(key, silent = false) {
        saveAuth({ ...(loadAuth() || {}), license_key: key });
        if (!silent) setGateLoading(true, 'Checking your license...');
        const auth = await authenticate(key);
        if (!auth || !auth.success) {
            const errorText = (auth && auth.error) || 'License check failed.';
            if (silent && isTransientError(errorText)) {
                scheduleSilentUnlock(key, 10000);
                return;
            }
            if (!uiRoot) showGate((auth && auth.error) || 'License check failed.');
            setGateLoading(false, (auth && auth.error) || 'License check failed.');
            setGateStatus((auth && auth.error) || 'License check failed.', true);
            return;
        }
        if (silentRetryTimer) {
            clearTimeout(silentRetryTimer);
            silentRetryTimer = null;
        }
        if (!silent) setGateLoading(true, 'Loading Nexus Free Bot...');
        try {
            await fetchAndRunBot();
        } catch(err) {
            const errorText = err && err.message ? err.message : 'Bot could not be loaded.';
            if (silent && isTransientError(errorText)) {
                scheduleSilentUnlock(key, 10000);
                return;
            }
            if (!uiRoot) showGate(errorText);
            setGateLoading(false, errorText);
            setGateStatus(errorText, true);
            return;
        }
        if (!silent) await showGateSuccess();
        removeGate();
        if (releaseEmbeddedBot) {
            const release = releaseEmbeddedBot;
            releaseEmbeddedBot = null;
            release();
        }
        if (heartbeatTimer) clearInterval(heartbeatTimer);
        heartbeatTimer = setInterval(heartbeat, 30000);
    }

    // Bu bir görsel "F12 engeli" değil: olay sunucuya gönderilir ve lisans
    // sunucu tarafında pasife alınır. Bu yüzden sayfa yenilense bile bot yüklenmez.
    function banCurrentScript(reason) {
        if (banRequestSent) return;
        banRequestSent = true;
        if (heartbeatTimer) clearInterval(heartbeatTimer);
        const saved = getSavedLicenseKey();
        gmRequest('POST', apiUrl(API_PREFIX + '/api/tamper/report'), {
            token: sessionToken,
            license_key: saved,
            client_id: CLIENT_ID,
            script_id: SCRIPT_ID,
            account_id: collectAccountId(),
            reason: reason || 'f12',
            source: 'cryptocrops_loader_keydown_v1',
            page: location.href,
            user_agent: navigator.userAgent
        }).finally(() => {
            sessionToken = '';
            loadedBotHash = '';
            saveAuth({});
            showGate('SCRIPT BANNED — lisans kilitlendi. Sayfa yenileniyor...');
            setGateStatus('SCRIPT BANNED — lisans kilitlendi. Sayfa yenileniyor...', true);
            setTimeout(() => location.reload(), 900);
        });
    }

    document.addEventListener('keydown', (event) => {
        const key = String(event.key || '').toUpperCase();
        const inspectShortcut = key === 'F12' || (event.ctrlKey && event.shiftKey && ['I', 'J', 'C'].includes(key));
        if (!inspectShortcut) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        banCurrentScript(key === 'F12' ? 'f12' : 'inspect_shortcut');
    }, true);

    function boot() {
        const savedKey = getSavedLicenseKey();
        if (savedKey) {
            unlockWithKey(savedKey, true);
            return;
        }
        showGate();
    }

    boot();
})();

__STATIC_BOT__
'''


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def api_json(method: str, url: str, payload=None, admin_token: str = ""):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
    }
    if admin_token:
        headers["x-admin-token"] = admin_token
    req = urlrequest.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urlrequest.urlopen(req, timeout=25) as res:
            raw = res.read().decode("utf-8", errors="replace")
            return json.loads(raw or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw or "{}")
        except Exception:
            body = {"detail": raw}
        raise RuntimeError(f"HTTP {exc.code}: {body}")
    except URLError as exc:
        raise RuntimeError(f"Baglanti hatasi: {exc}")


def safe_name(value: str, fallback: str = "User") -> str:
    out = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value or "").strip())
    return out or fallback


def embed_bot_for_loader(source: str) -> str:
    """Keep the bot in the userscript sandbox so its GM_* grants survive CSP."""
    marker = "(function(){"
    if marker not in source:
        raise RuntimeError("Bot başlangıç yapısı bulunamadı")
    return source.replace(
        marker,
        "(async function(){ await globalThis.__NEXUS_CROPCROPS_ULTRA_START__;",
        1,
    )


def validate_bot_source(source: str) -> None:
    """Fail early instead of creating a broken userscript from invalid JS."""
    try:
        result = subprocess.run(
            ["node", "--check"],
            input=source,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Node.js bulunamadı; bot syntax kontrolü yapılamıyor") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Bot syntax kontrolü zaman aşımına uğradı") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "Bilinmeyen JavaScript syntax hatası").strip()
        raise RuntimeError("Bot söz dizimi hatalı:\n" + detail)


def render_client_script(name: str, client_id: str, script_id: str, server_url: str, bot_source: str) -> str:
    host = urlparse(server_url).netloc
    return (CLIENT_TEMPLATE
            .replace("__CLIENT_NAME__", name)
            .replace("__CLIENT_ID__", client_id)
            .replace("__SCRIPT_ID__", script_id)
            .replace("__SERVER_URL__", server_url)
            .replace("__SERVER_HOST__", host)
            .replace("__SCRIPT_BUILD__", str(int(time.time())))
            .replace("__STATIC_BOT__", embed_bot_for_loader(bot_source)))


class CryptoCropsUltraPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Nexus CryptoCrops Ultra - Lisans Paneli")
        self.geometry("1080x720")
        self.minsize(980, 640)
        self.configure(bg="#102418")
        self.settings = {**DEFAULT_SETTINGS, **load_json(SETTINGS_FILE, {})}
        self.licenses_cache = []
        self.server_var = tk.StringVar(value=self.settings.get("server_url", ""))
        self.admin_var = tk.StringVar(value=self.settings.get("admin_token", ""))
        self.bot_path_var = tk.StringVar(value=self.settings.get("selected_bot_path", str(BOT_FILE)))
        self.license_name_var = tk.StringVar(value="User1")
        self.license_key_var = tk.StringVar(value="")
        self.multi_var = tk.BooleanVar(value=False)
        self.server_status_var = tk.StringVar(value="Cloudflare: kontrol ediliyor | Render: kontrol ediliyor")
        self.tree_menu = None
        self.build_ui()
        self.after(350, self.refresh_server_status)
        self.refresh_licenses(silent=True)

    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background="#173323", foreground="#f7f0d6", fieldbackground="#173323", rowheight=28)
        style.configure("Treeview.Heading", background="#355d35", foreground="#fff8df", font=("Segoe UI", 10, "bold"))

        header = tk.Frame(self, bg="#102418")
        header.pack(fill="x", padx=18, pady=(16, 10))
        tk.Label(header, text="🌾  NEXUS CROPCROPS ULTRA", bg="#102418", fg="#f5c84c", font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(header, textvariable=self.server_status_var, bg="#102418", fg="#7ee787", font=("Segoe UI", 10, "bold")).pack(side="right")

        main = tk.Frame(self, bg="#102418")
        main.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        left = tk.Frame(main, bg="#102418")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(main, bg="#102418", width=360)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        list_head = tk.Frame(left, bg="#102418")
        list_head.pack(fill="x", pady=(0, 8))
        tk.Label(list_head, text="Hasat Lisansları", bg="#102418", fg="#fff2be", font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Button(list_head, text="Lisansları Yenile", command=self.refresh_licenses, bg="#587b35", fg="white", relief="flat", padx=18).pack(side="right")

        columns = ("name", "key", "active", "account", "online")
        self.tree = ttk.Treeview(left, columns=columns, show="headings")
        self.tree.heading("name", text="Isim")
        self.tree.heading("key", text="Key")
        self.tree.heading("active", text="Aktif")
        self.tree.heading("account", text="Hesap")
        self.tree.heading("online", text="Status")
        self.tree.column("name", width=140)
        self.tree.column("key", width=210)
        self.tree.column("active", width=70, anchor="center")
        self.tree.column("account", width=180)
        self.tree.column("online", width=80, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.show_selected_details())
        self.tree.bind("<Button-3>", self.show_tree_menu)

        self.tree_menu = tk.Menu(self, tearoff=0, bg="#111827", fg="white", activebackground="#2563eb", activeforeground="white")
        self.tree_menu.add_command(label="Key Kopyala", command=lambda: self.copy_tree_value(1, "Key kopyalandi"))
        self.tree_menu.add_command(label="Key Duzenle", command=self.edit_selected_key)
        self.tree_menu.add_command(label="Client ID Kopyala", command=self.copy_selected_client_id)
        self.tree_menu.add_separator()
        self.tree_menu.add_command(label="Aktif Yap", command=lambda: self.toggle_selected(active=True))
        self.tree_menu.add_command(label="Pasif Yap", command=lambda: self.toggle_selected(active=False))
        self.tree_menu.add_command(label="Script Ban Kaldır", command=self.clear_selected_ban)
        self.tree_menu.add_command(label="Coklu Hesap Ac", command=lambda: self.toggle_selected(multi_account=True))
        self.tree_menu.add_command(label="Tek Hesap Yap", command=lambda: self.toggle_selected(multi_account=False))
        self.tree_menu.add_command(label="Hesap Bagini Sifirla", command=lambda: self.toggle_selected(reset_account=True))
        self.tree_menu.add_separator()
        self.tree_menu.add_command(label="Sil", command=self.delete_selected)

        bot_box = tk.LabelFrame(right, text="🌱 Bot Tohumu", bg="#102418", fg="#f5c84c", bd=1, relief="solid")
        bot_box.pack(fill="x", pady=(0, 12))
        tk.Entry(bot_box, textvariable=self.bot_path_var, bg="#173323", fg="#fff8df", insertbackground="#fff8df", relief="flat").pack(fill="x", padx=10, pady=(10, 8), ipady=7)
        bot_actions = tk.Frame(bot_box, bg="#102418")
        bot_actions.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(bot_actions, text="Dosya Seç", command=self.choose_bot, bg="#805b2d", fg="white", relief="flat", padx=14).pack(side="left", fill="x", expand=True)
        tk.Button(bot_actions, text="Sunucuya Ekle", command=self.upload_bot, bg="#587b35", fg="white", relief="flat", padx=14).pack(side="left", fill="x", expand=True, padx=(8, 0))

        create_box = tk.LabelFrame(right, text="🔑 Ultra Script Üret", bg="#102418", fg="#f5c84c", bd=1, relief="solid")
        create_box.pack(fill="x", pady=(0, 12))
        tk.Label(create_box, text="Çiftlik sahibi", bg="#102418", fg="#b6d8a9").pack(anchor="w", padx=10, pady=(10, 2))
        tk.Entry(create_box, textvariable=self.license_name_var, bg="#173323", fg="#fff8df", insertbackground="#fff8df", relief="flat").pack(fill="x", padx=10, ipady=7)
        tk.Label(create_box, text="Lisans anahtarı (boşsa üretilir)", bg="#102418", fg="#b6d8a9").pack(anchor="w", padx=10, pady=(8, 2))
        tk.Entry(create_box, textvariable=self.license_key_var, bg="#173323", fg="#fff8df", insertbackground="#fff8df", relief="flat").pack(fill="x", padx=10, ipady=7)
        tk.Checkbutton(create_box, text="Çoklu hesap", variable=self.multi_var, bg="#102418", fg="#e9f5d9", selectcolor="#173323", activebackground="#102418", activeforeground="#ffffff").pack(anchor="w", padx=10, pady=8)
        tk.Button(create_box, text="🌾 Key + Script Üret", command=self.generate_script, bg="#c17c26", fg="white", relief="flat").pack(fill="x", padx=10, pady=(0, 10), ipady=8)

        self.details = scrolledtext.ScrolledText(right, height=15, bg="#173323", fg="#fff8df", insertbackground="#fff8df", relief="flat", font=("Consolas", 9))
        self.details.pack(fill="both", expand=True, pady=(0, 10))
        self.log = scrolledtext.ScrolledText(right, height=10, bg="#0c1a10", fg="#ccebbf", insertbackground="#ccebbf", relief="flat", font=("Consolas", 9))
        self.log.pack(fill="both")

    def save_settings(self):
        self.settings.update({
            "server_url": self.server_var.get().strip().rstrip("/"),
            "admin_token": self.admin_var.get().strip(),
            "selected_bot_path": self.bot_path_var.get().strip(),
        })
        save_json(SETTINGS_FILE, self.settings)
        self.log_line("Ayarlar kaydedildi")

    def choose_bot(self):
        path = filedialog.askopenfilename(initialdir=str(ROOT_DIR), title="Bot dosyasi sec", filetypes=[("Text/JS", "*.txt *.js"), ("All", "*.*")])
        if path:
            self.bot_path_var.set(path)
            self.save_settings()

    def upload_bot(self):
        try:
            self.save_settings()
            path = Path(self.bot_path_var.get().strip())
            content = path.read_text(encoding="utf-8", errors="replace")
            validate_bot_source(content)
            res = api_json("POST", self.server_url("/admin/bot/upload"), {"file_name": path.name, "content": content}, self.admin_var.get().strip())
            self.log_line("Bot upload: " + json.dumps(res.get("bot") or res, ensure_ascii=False))
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Bot yuklenemedi")
            updated = self.refresh_generated_scripts(content)
            messagebox.showinfo("Tamam", f"Bot servera yüklendi.\nYerel script güncellemesi: {updated}")
        except Exception as exc:
            self.log_line("Bot upload hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def generate_script(self):
        try:
            self.save_settings()
            bot_path = Path(self.bot_path_var.get().strip())
            if not bot_path.is_file():
                raise RuntimeError("Bot dosyası bulunamadı")
            content = bot_path.read_text(encoding="utf-8", errors="replace")
            if not content.strip():
                raise RuntimeError("Bot dosyası boş")
            validate_bot_source(content)
            client_id = "ccu_" + secrets.token_hex(8)
            script_id = "script_" + secrets.token_hex(8)
            user_name = self.license_name_var.get().strip() or self.next_user_name()
            if self.is_reserved_user_name(user_name):
                user_name = self.next_user_name()
                self.license_name_var.set(user_name)
            manual_key = self.license_key_var.get().strip()
            payload = {
                "name": user_name,
                "active": True,
                "multi_account": bool(self.multi_var.get()),
                "allowed_client_id": client_id,
            }
            if manual_key:
                payload["key"] = manual_key
            lic_res = api_json("POST", self.server_url("/admin/license/create"), payload, self.admin_var.get().strip())
            if not lic_res.get("success"):
                raise RuntimeError(lic_res.get("error") or "Lisans olusmadi")
            lic = lic_res["license"]
            server_url = self.server_var.get().strip().rstrip("/")
            script = render_client_script(user_name, client_id, script_id, server_url, content)
            out_path = GENERATED_DIR / f"{safe_name(user_name)}_{client_id[:8]}.user.js"
            out_path.write_text(script, encoding="utf-8")
            index = load_json(SCRIPT_INDEX_FILE, {})
            index[str(lic.get("id") or "")] = str(out_path)
            save_json(SCRIPT_INDEX_FILE, index)
            self.publish_script_package(str(lic.get("id") or ""), client_id, script_id, script)
            self.log_line("Script uretildi: " + str(out_path))
            self.refresh_licenses(silent=True)
            self.license_name_var.set(self.next_user_name())
            self.license_key_var.set("")
            messagebox.showinfo("Tamam", f"Script hazir:\n{out_path}\n\nKullanici key ekraninda bu keyi girecek:\n{lic.get('key', '')}")
        except Exception as exc:
            self.log_line("Script hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def publish_script_package(self, license_id: str, client_id: str, script_id: str, content: str) -> None:
        if not license_id:
            return
        result = api_json("POST", self.server_url("/admin/script/upload"), {
            "license_id": license_id,
            "client_id": client_id,
            "script_id": script_id,
            "content": content,
        }, self.admin_var.get().strip())
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "Script guncelleme paketi yuklenemedi")

    def refresh_generated_scripts(self, content: str) -> int:
        """Refresh the bot payload in panel-managed script files after an upload."""
        updated = 0
        index = load_json(SCRIPT_INDEX_FILE, {})
        license_by_path = {str(Path(value).resolve()): license_id for license_id, value in index.items()}
        for path in GENERATED_DIR.glob("*.user.js"):
            try:
                existing = path.read_text(encoding="utf-8", errors="replace")
                name = re.search(r"const CLIENT_NAME = '([^']*)';", existing)
                client_id = re.search(r"const CLIENT_ID = '([^']*)';", existing)
                script_id = re.search(r"const SCRIPT_ID = '([^']*)';", existing)
                server_url = re.search(r"const SERVER_URL = '([^']*)';", existing)
                if not all((name, client_id, script_id, server_url)):
                    continue
                fresh = render_client_script(name.group(1), client_id.group(1), script_id.group(1), server_url.group(1), content)
                validate_bot_source(fresh)
                path.write_text(fresh, encoding="utf-8")
                self.publish_script_package(license_by_path.get(str(path.resolve()), ""), client_id.group(1), script_id.group(1), fresh)
                updated += 1
            except Exception as exc:
                self.log_line(f"Script güncellenemedi ({path.name}): {exc}")
        if updated:
            self.log_line(f"Yeni bot {updated} yerel script dosyasına işlendi")
        return updated

    def refresh_licenses(self, silent=False):
        try:
            res = api_json("GET", self.server_url("/admin/licenses"), None, self.admin_var.get().strip())
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Liste alinamadi")
            self.licenses_cache = res.get("licenses") or []
            self.sync_deleted_script_files()
            self.refresh_tree()
            if not silent:
                self.log_line(f"Lisans listesi yenilendi: {len(self.licenses_cache)}")
            current_name = self.license_name_var.get().strip()
            if not current_name or self.is_reserved_user_name(current_name):
                self.license_name_var.set(self.next_user_name())
        except Exception as exc:
            if not silent:
                self.log_line("Lisans liste hata: " + str(exc))

    def sync_deleted_script_files(self):
        """Panel dışından silinen oluşturulmuş scriptleri lisans listesiyle eşitler."""
        index = load_json(SCRIPT_INDEX_FILE, {})
        changed = False
        for license_id, path_text in list(index.items()):
            path = Path(str(path_text))
            if path.is_file():
                continue
            try:
                res = api_json(
                    "POST",
                    self.server_url("/admin/license/delete"),
                    {"license_id": license_id},
                    self.admin_var.get().strip(),
                )
                if res.get("success"):
                    self.licenses_cache = [x for x in self.licenses_cache if str(x.get("id") or "") != str(license_id)]
                    self.log_line("Dosyası silinen script panelden kaldırıldı: " + str(license_id))
            except Exception as exc:
                self.log_line("Silinen dosya eşitleme hata: " + str(exc))
            index.pop(license_id, None)
            changed = True
        if changed:
            save_json(SCRIPT_INDEX_FILE, index)

    def refresh_tree(self):
        selected_key = ""
        focused = self.tree.focus()
        if focused:
            values = self.tree.item(focused, "values")
            selected_key = values[1] if values and len(values) > 1 else ""
        for item in self.tree.get_children():
            self.tree.delete(item)
        refocus = None
        for lic in self.licenses_cache:
            item = self.tree.insert("", "end", values=(
                lic.get("name", ""),
                lic.get("key", ""),
                "EVET" if lic.get("active") else "HAYIR",
                lic.get("account_id", "") or "-",
                "F12" if lic.get("tamper_detected") else ("EVET" if lic.get("online") else "HAYIR"),
            ))
            if selected_key and lic.get("key") == selected_key:
                refocus = item
        if refocus:
            self.tree.selection_set(refocus)
            self.tree.focus(refocus)
        self.show_selected_details()

    def show_tree_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self.tree.selection_set(row_id)
        self.tree.focus(row_id)
        self.tree_menu.tk_popup(event.x_root, event.y_root)
        self.tree_menu.grab_release()

    def get_selected_license(self):
        selected = self.tree.focus()
        if not selected:
            return None
        values = self.tree.item(selected, "values")
        key = values[1] if values and len(values) > 1 else ""
        return next((x for x in self.licenses_cache if x.get("key") == key), None)

    def show_selected_details(self):
        lic = self.get_selected_license()
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        if not lic:
            self.details.insert("1.0", "Soldan lisans sec.\n")
        else:
            self.details.insert("1.0", json.dumps(lic, ensure_ascii=False, indent=2))
        self.details.configure(state="disabled")

    def copy_tree_value(self, index: int, ok_text: str):
        selected = self.tree.focus()
        if not selected:
            return
        values = self.tree.item(selected, "values")
        if not values or index >= len(values):
            return
        value = str(values[index] or "")
        if not value or value == "-":
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.log_line(ok_text)

    def copy_selected_client_id(self):
        lic = self.get_selected_license()
        if not lic:
            return
        value = lic.get("allowed_client_id") or lic.get("client_id") or ""
        if value:
            self.clipboard_clear()
            self.clipboard_append(str(value))
            self.log_line("Client ID kopyalandi")

    def edit_selected_key(self):
        try:
            lic = self.get_selected_license()
            if not lic:
                return
            old_key = lic.get("key", "")
            new_key = simpledialog.askstring("Key Duzenle", "Yeni key:", initialvalue=old_key, parent=self)
            if new_key is None:
                return
            new_key = new_key.strip()
            if not new_key:
                raise RuntimeError("Key bos olamaz")
            res = api_json("POST", self.server_url("/admin/license/key"), {"license_id": lic.get("id", ""), "key": new_key}, self.admin_var.get().strip())
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Key guncellenemedi")
            self.refresh_licenses(silent=True)
            self.log_line("Key guncellendi")
        except Exception as exc:
            self.log_line("Key duzenleme hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def toggle_selected(self, active=None, multi_account=None, reset_account=False):
        try:
            lic = self.get_selected_license()
            if not lic:
                return
            payload = {"license_id": lic.get("id", "")}
            if active is not None:
                payload["active"] = bool(active)
            if multi_account is not None:
                payload["multi_account"] = bool(multi_account)
            if reset_account:
                payload["reset_account"] = True
            res = api_json("POST", self.server_url("/admin/license/toggle"), payload, self.admin_var.get().strip())
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Guncellenemedi")
            self.refresh_licenses(silent=True)
            self.log_line("Lisans guncellendi")
        except Exception as exc:
            self.log_line("Lisans guncelleme hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def clear_selected_ban(self):
        try:
            lic = self.get_selected_license()
            if not lic:
                return
            res = api_json("POST", self.server_url("/admin/license/tamper-clear"), {"license_id": lic.get("id", "")}, self.admin_var.get().strip())
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Ban kaldırılamadı")
            self.refresh_licenses(silent=True)
            self.log_line("Script ban kaldırıldı; lisansı tekrar aktif yapabilirsin")
            messagebox.showinfo("Tamam", "Ban kaldırıldı. Gerekirse sağ tık > Aktif Yap kullan.")
        except Exception as exc:
            self.log_line("Ban kaldırma hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def delete_selected(self):
        try:
            lic = self.get_selected_license()
            if not lic:
                return
            if not messagebox.askyesno("Sil", f"{lic.get('name') or 'Lisans'} silinsin mi?"):
                return
            res = api_json("POST", self.server_url("/admin/license/delete"), {"license_id": lic.get("id", "")}, self.admin_var.get().strip())
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Silinemedi")
            index = load_json(SCRIPT_INDEX_FILE, {})
            script_path = Path(str(index.pop(str(lic.get("id") or ""), "")))
            if script_path and script_path.is_file():
                generated_root = GENERATED_DIR.resolve()
                resolved_script = script_path.resolve()
                if generated_root == resolved_script.parent:
                    script_path.unlink()
                    self.log_line("Script dosyası silindi: " + str(script_path))
            save_json(SCRIPT_INDEX_FILE, index)
            self.refresh_licenses(silent=True)
            self.log_line("Lisans ve script silindi")
        except Exception as exc:
            self.log_line("Silme hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def health_check(self):
        try:
            res = api_json("GET", self.server_url("/health"), None, "")
            self.log_line("Health: " + json.dumps(res, ensure_ascii=False))
            messagebox.showinfo("Health", json.dumps(res, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.log_line("Health hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def refresh_server_status(self):
        try:
            base = self.server_var.get().strip().rstrip("/")
            res = api_json("GET", base + "/__router/status", None, self.admin_var.get().strip())
            mode = str(res.get("mode") or "secondary")
            if mode == "primary":
                self.server_status_var.set("Render: AKTIF  |  Cloudflare: BEKLEME")
            else:
                self.server_status_var.set("Cloudflare: AKTIF  |  Render: BEKLEME")
        except Exception:
            self.server_status_var.set("Cloudflare Gateway: BAGLANTI HATASI")

    def server_url(self, path: str) -> str:
        return self.server_var.get().strip().rstrip("/") + "/cryptocrops" + path

    def next_user_name(self) -> str:
        used = self.collect_used_user_numbers()
        idx = 1
        while idx in used:
            idx += 1
        return f"User{idx}"

    def is_reserved_user_name(self, name: str) -> bool:
        match = re.fullmatch(r"user\s*(\d+)", str(name or "").strip(), flags=re.IGNORECASE)
        if not match:
            return False
        return int(match.group(1)) in self.collect_used_user_numbers()

    def collect_used_user_numbers(self) -> set[int]:
        used: set[int] = set()
        for lic in self.licenses_cache:
            self.add_user_number(used, str(lic.get("name") or ""))
        for path in GENERATED_DIR.glob("User*.user.js"):
            self.add_user_number(used, path.stem.split("_", 1)[0])
        for path_text in load_json(SCRIPT_INDEX_FILE, {}).values():
            self.add_user_number(used, Path(str(path_text)).stem.split("_", 1)[0])
        return used

    @staticmethod
    def add_user_number(used: set[int], name: str) -> None:
        match = re.fullmatch(r"user\s*(\d+)", str(name or "").strip(), flags=re.IGNORECASE)
        if match:
            used.add(int(match.group(1)))

    def log_line(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")


if __name__ == "__main__":
    CryptoCropsUltraPanel().mainloop()
