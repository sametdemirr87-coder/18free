#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import re
import secrets
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
SETTINGS_FILE = BASE_DIR / "flash_panel_settings.json"
BOT_FILE = ROOT_DIR / "BOT2.txt"
GENERATED_DIR = BASE_DIR / "generated_flash_scripts"
GENERATED_DIR.mkdir(exist_ok=True)
SCRIPT_INDEX_FILE = BASE_DIR / "generated_flash_scripts_index.json"

DEFAULT_SETTINGS = {
    "server_url": "https://one8free.onrender.com",
    "admin_token": "MbfAdmin_18free!7429",
    "selected_bot_path": str(BOT_FILE),
}

CLIENT_TEMPLATE = r'''// ==UserScript==
// @name         __CLIENT_NAME__
// @namespace    flashminers
// @version      1.0.0
// @description  Nexus FlashMiners Bot secure loader
// @match        https://flashyminers.com/*
// @match        https://flashyminers.com/games*
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
    const STORAGE_KEY = 'flashminers_auth_' + CLIENT_ID;
    const GLOBAL_STORAGE_KEY = 'flashminers_auth_latest';
    const TELEGRAM_URL = 'https://t.me/+cxRPV2-7C_Y0Yjc0';
    const TELEGRAM_ICON = 'https://telegram.org/img/favicon.ico';
    let sessionToken = '';
    let loadedBotHash = '';
    let heartbeatTimer = null;
    let uiRoot = null;
    let reauthInProgress = false;
    let silentRetryTimer = null;

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
        const candidates = [];
        const push = (value) => {
            value = String(value || '').trim();
            if (value && !candidates.includes(value)) candidates.push(value);
        };
        try {
            ['user_id', 'userId', 'account_id', 'accountId', 'flashminers_user'].forEach((key) => {
                push(localStorage.getItem(key));
                push(sessionStorage.getItem(key));
            });
        } catch(e) {}
        try {
            const text = document.body ? document.body.innerText : '';
            const match = String(text || '').match(/(?:User|ID|Account)\s*#?\s*:?\s*([A-Za-z0-9_.@-]{4,80})/i);
            if (match) push(match[1]);
        } catch(e) {}
        if (candidates[0]) return candidates[0];
        try {
            let fp = localStorage.getItem('flashminers_device_id') || '';
            if (!fp) {
                fp = 'dev_' + Math.random().toString(16).slice(2) + Date.now().toString(16);
                localStorage.setItem('flashminers_device_id', fp);
            }
            return fp;
        } catch(e) {
            return CLIENT_ID;
        }
    }

    function getSavedLicenseKey() {
        return String((loadAuth() || {}).license_key || '').trim();
    }

    function showGate(message = '') {
        try {
            removeGate();
            const saved = getSavedLicenseKey();
            uiRoot = document.createElement('div');
            uiRoot.id = 'nexusFreeGate';
            uiRoot.innerHTML = `
                <style>
                    #nexusFreeGate { position:fixed; inset:0; z-index:2147483647; display:grid; place-items:center; font-family:Inter,Segoe UI,Arial,sans-serif; color:#fff8dc; background:radial-gradient(circle at 50% 18%, rgba(250,204,21,.20), transparent 33%), radial-gradient(circle at 20% 80%, rgba(180,83,9,.16), transparent 28%), linear-gradient(180deg, rgba(8,6,2,.88), rgba(1,1,1,.98)); backdrop-filter:blur(16px); }
                    .nfg-card { width:min(410px, calc(100vw - 32px)); border:1px solid rgba(250,204,21,.44); background:linear-gradient(180deg, rgba(20,15,5,.96), rgba(3,3,3,.98)); box-shadow:0 28px 90px rgba(0,0,0,.62), 0 0 55px rgba(234,179,8,.24), inset 0 1px 0 rgba(255,255,255,.08); border-radius:24px; padding:28px; position:relative; overflow:hidden; animation:nfgIn .65s cubic-bezier(.2,.9,.2,1) both; }
                    .nfg-card:before { content:""; position:absolute; inset:-2px; background:linear-gradient(115deg, transparent, rgba(250,204,21,.23), transparent); transform:translateX(-120%); animation:nfgSweep 2.8s ease-in-out infinite; }
                    .nfg-card:after { content:""; position:absolute; inset:1px; border-radius:22px; pointer-events:none; border:1px solid rgba(255,255,255,.04); }
                    .nfg-top { position:relative; display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:18px; }
                    .nfg-brand { display:grid; gap:4px; }
                    .nfg-title { font-size:28px; line-height:1; font-weight:950; letter-spacing:.4px; color:#facc15; text-shadow:0 0 24px rgba(250,204,21,.32); }
                    .nfg-sub { color:#d6a93b; font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:2.5px; }
                    .nfg-tg { width:46px; height:46px; border-radius:50%; display:grid; place-items:center; background:rgba(15,23,42,.72); border:1px solid rgba(250,204,21,.36); cursor:pointer; box-shadow:0 0 28px rgba(34,158,217,.36); position:relative; padding:0; }
                    .nfg-tg img { width:32px; height:32px; display:block; }
                    .nfg-label { position:relative; color:#facc15; font-size:12px; font-weight:900; margin:16px 0 8px; letter-spacing:.6px; }
                    .nfg-input { position:relative; width:100%; box-sizing:border-box; border:1px solid rgba(250,204,21,.28); background:rgba(0,0,0,.72); color:#fff8dc; border-radius:14px; padding:14px 15px; outline:none; font-size:14px; font-weight:900; letter-spacing:.5px; }
                    .nfg-input::placeholder { color:rgba(250,204,21,.42); }
                    .nfg-input:focus { border-color:#facc15; box-shadow:0 0 0 4px rgba(250,204,21,.12); }
                    .nfg-btn { position:relative; width:100%; margin-top:14px; border:0; border-radius:14px; padding:14px; color:#111; font-weight:950; letter-spacing:1.4px; background:linear-gradient(135deg,#facc15,#f59e0b,#fde68a); cursor:pointer; box-shadow:0 18px 40px rgba(250,204,21,.30); }
                    .nfg-btn:hover { filter:brightness(1.12); transform:translateY(-1px); }
                    .nfg-status { position:relative; min-height:18px; color:#facc15; font-size:12px; font-weight:900; margin-top:12px; text-align:center; }
                    .nfg-loader { display:none; position:relative; width:54px; height:54px; margin:18px auto 2px; border-radius:50%; border:4px solid rgba(250,204,21,.18); border-top-color:#facc15; animation:nfgSpin .8s linear infinite; }
                    .nfg-loading .nfg-loader { display:block; }
                    .nfg-loading .nfg-btn, .nfg-loading .nfg-input { opacity:.52; pointer-events:none; }
                    .nfg-burst { position:absolute; inset:50%; width:12px; height:12px; border-radius:50%; background:#facc15; transform:translate(-50%,-50%) scale(0); pointer-events:none; }
                    .nfg-success .nfg-burst { animation:nfgBurst .75s ease-out forwards; }
                    .nfg-mini { position:relative; margin-top:10px; color:rgba(255,248,220,.48); text-align:center; font-size:11px; font-weight:800; }
                    @keyframes nfgIn { from { opacity:0; transform:translateY(18px) scale(.94); filter:blur(8px); } to { opacity:1; transform:none; filter:none; } }
                    @keyframes nfgSweep { 45%,100% { transform:translateX(120%); } }
                    @keyframes nfgSpin { to { transform:rotate(360deg); } }
                    @keyframes nfgBurst { 0% { transform:translate(-50%,-50%) scale(0); opacity:.95; } 60% { transform:translate(-50%,-50%) scale(75); opacity:.55; } 100% { transform:translate(-50%,-50%) scale(95); opacity:0; } }
                </style>
                <div class="nfg-card">
                    <div class="nfg-burst"></div>
                    <div class="nfg-top">
                        <div class="nfg-brand">
                            <div class="nfg-sub">Secure access</div>
                            <div class="nfg-title">Nexus Flash Bot</div>
                        </div>
                        <button class="nfg-tg" id="nfgTelegram" title="Open Telegram"><img src="${TELEGRAM_ICON}" alt=""></button>
                    </div>
                    <label class="nfg-label" for="nfgKey">License key</label>
                    <input class="nfg-input" id="nfgKey" placeholder="Enter your license key" value="${escapeAttr(saved)}" autocomplete="off">
                    <button class="nfg-btn" id="nfgUnlock">UNLOCK BOT</button>
                    <div class="nfg-loader"></div>
                    <div class="nfg-status" id="nfgStatus">${escapeHtml(message || 'Enter your key to continue.')}</div>
                    <div class="nfg-mini">FLASHMINERS ACCESS</div>
                </div>
            `;
            document.documentElement.appendChild(uiRoot);
            document.getElementById('nfgTelegram').onclick = () => window.open(TELEGRAM_URL, '_blank', 'noopener,noreferrer');
            document.getElementById('nfgUnlock').onclick = async () => {
                const key = String(document.getElementById('nfgKey').value || '').trim();
                if (!key) {
                    setGateStatus('Please enter a license key.', true);
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
        status.style.color = bad ? '#f87171' : '#93c5fd';
    }

    function showGateSuccess() {
        return new Promise((resolve) => {
            if (!uiRoot) return resolve();
            const card = uiRoot.querySelector('.nfg-card');
            if (card) card.classList.add('nfg-success');
            setGateStatus('Access granted. Launching bot...', false);
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
        const res = await gmRequest('POST', apiUrl('/flash/api/auth'), {
            license_key: licenseKey,
            client_id: CLIENT_ID,
            script_id: SCRIPT_ID,
            account_id: accountId,
            page: location.href,
            user_agent: navigator.userAgent
        });
        if (res && res.success) {
            sessionToken = res.token || '';
            saveAuth({ license_key: licenseKey, session_token: sessionToken, account_id: accountId });
        }
        return res;
    }

    async function heartbeat() {
        if (!sessionToken) return;
        const res = await gmRequest('POST', apiUrl('/flash/api/heartbeat'), {
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
        const qs = '?token=' + encodeURIComponent(sessionToken)
            + '&client_id=' + encodeURIComponent(CLIENT_ID)
            + '&script_id=' + encodeURIComponent(SCRIPT_ID)
            + '&account_id=' + encodeURIComponent(collectAccountId());
        const bundle = await gmGet(apiUrl('/flash/api/bot/bundle') + qs);
        if (!bundle || !bundle.success) {
            throw new Error((bundle && bundle.error) || 'Bot could not be loaded');
        }
        if (bundle.hash && loadedBotHash === bundle.hash) return;
        const code = decryptBot(bundle.encrypted || '');
        loadedBotHash = bundle.hash || '';
        window.__MINERBYTSFREE_CLIENT__ = {
            serverUrl: SERVER_URL,
            clientId: CLIENT_ID,
            scriptId: SCRIPT_ID,
            sessionToken,
            accountId: collectAccountId(),
            botHash: loadedBotHash
        };
        (0, eval)(code);
        injectTelegramButton();
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
        if (!silent) setGateLoading(true, 'Loading Nexus Flash Bot...');
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
        if (heartbeatTimer) clearInterval(heartbeatTimer);
        heartbeatTimer = setInterval(heartbeat, 30000);
    }

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
    headers = {"Content-Type": "application/json"}
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


class FlashMinersPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FlashMiners Server Panel")
        self.geometry("1080x720")
        self.minsize(980, 640)
        self.configure(bg="#0b1020")
        self.settings = {**DEFAULT_SETTINGS, **load_json(SETTINGS_FILE, {})}
        self.licenses_cache = []
        self.server_var = tk.StringVar(value=self.settings.get("server_url", ""))
        self.admin_var = tk.StringVar(value=self.settings.get("admin_token", ""))
        self.bot_path_var = tk.StringVar(value=self.settings.get("selected_bot_path", str(BOT_FILE)))
        self.license_name_var = tk.StringVar(value="User1")
        self.license_key_var = tk.StringVar(value="")
        self.multi_var = tk.BooleanVar(value=False)
        self.tree_menu = None
        self.build_ui()
        self.refresh_licenses(silent=True)

    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background="#111827", foreground="#e5e7eb", fieldbackground="#111827", rowheight=28)
        style.configure("Treeview.Heading", background="#1f2937", foreground="#f9fafb", font=("Segoe UI", 10, "bold"))

        header = tk.Frame(self, bg="#0b1020")
        header.pack(fill="x", padx=18, pady=(16, 10))
        tk.Label(header, text="FLASHMINERS VIP PANEL", bg="#0b1020", fg="#60a5fa", font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(header, text="Server bagli: one8free.onrender.com", bg="#0b1020", fg="#64748b", font=("Segoe UI", 10, "bold")).pack(side="right")

        main = tk.Frame(self, bg="#0b1020")
        main.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        left = tk.Frame(main, bg="#0b1020")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(main, bg="#0b1020", width=360)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        list_head = tk.Frame(left, bg="#0b1020")
        list_head.pack(fill="x", pady=(0, 8))
        tk.Label(list_head, text="Uretilen Lisanslar", bg="#0b1020", fg="#e5e7eb", font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Button(list_head, text="Lisanslari Yenile", command=self.refresh_licenses, bg="#2563eb", fg="white", relief="flat", padx=18).pack(side="right")

        columns = ("name", "key", "active", "account", "online")
        self.tree = ttk.Treeview(left, columns=columns, show="headings")
        self.tree.heading("name", text="Isim")
        self.tree.heading("key", text="Key")
        self.tree.heading("active", text="Aktif")
        self.tree.heading("account", text="Hesap")
        self.tree.heading("online", text="Online")
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
        self.tree_menu.add_command(label="Coklu Hesap Ac", command=lambda: self.toggle_selected(multi_account=True))
        self.tree_menu.add_command(label="Tek Hesap Yap", command=lambda: self.toggle_selected(multi_account=False))
        self.tree_menu.add_command(label="Hesap Bagini Sifirla", command=lambda: self.toggle_selected(reset_account=True))
        self.tree_menu.add_separator()
        self.tree_menu.add_command(label="Sil", command=self.delete_selected)

        bot_box = tk.LabelFrame(right, text="Bot Yukleme", bg="#0b1020", fg="#93c5fd", bd=1, relief="solid")
        bot_box.pack(fill="x", pady=(0, 12))
        tk.Entry(bot_box, textvariable=self.bot_path_var, bg="#111827", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat").pack(fill="x", padx=10, pady=(10, 8), ipady=7)
        bot_actions = tk.Frame(bot_box, bg="#0b1020")
        bot_actions.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(bot_actions, text="Bot Sec", command=self.choose_bot, bg="#334155", fg="white", relief="flat", padx=14).pack(side="left", fill="x", expand=True)
        tk.Button(bot_actions, text="Botu Servera Yukle", command=self.upload_bot, bg="#16a34a", fg="white", relief="flat", padx=14).pack(side="left", fill="x", expand=True, padx=(8, 0))

        create_box = tk.LabelFrame(right, text="Script Uret", bg="#0b1020", fg="#93c5fd", bd=1, relief="solid")
        create_box.pack(fill="x", pady=(0, 12))
        tk.Label(create_box, text="Kullanici adi", bg="#0b1020", fg="#94a3b8").pack(anchor="w", padx=10, pady=(10, 2))
        tk.Entry(create_box, textvariable=self.license_name_var, bg="#111827", fg="#f8fafc", insertbackground="#f8fafc", relief="flat").pack(fill="x", padx=10, ipady=7)
        tk.Label(create_box, text="License key", bg="#0b1020", fg="#94a3b8").pack(anchor="w", padx=10, pady=(8, 2))
        tk.Entry(create_box, textvariable=self.license_key_var, bg="#111827", fg="#f8fafc", insertbackground="#f8fafc", relief="flat").pack(fill="x", padx=10, ipady=7)
        tk.Checkbutton(create_box, text="Coklu hesap", variable=self.multi_var, bg="#0b1020", fg="#dbeafe", selectcolor="#111827", activebackground="#0b1020", activeforeground="#ffffff").pack(anchor="w", padx=10, pady=8)
        tk.Button(create_box, text="Key + Script Uret", command=self.generate_script, bg="#7c3aed", fg="white", relief="flat").pack(fill="x", padx=10, pady=(0, 10), ipady=8)

        self.details = scrolledtext.ScrolledText(right, height=15, bg="#111827", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat", font=("Consolas", 9))
        self.details.pack(fill="both", expand=True, pady=(0, 10))
        self.log = scrolledtext.ScrolledText(right, height=10, bg="#020617", fg="#bfdbfe", insertbackground="#bfdbfe", relief="flat", font=("Consolas", 9))
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
            res = api_json("POST", self.server_url("/flash/admin/bot/upload"), {"file_name": path.name, "content": content}, self.admin_var.get().strip())
            self.log_line("Bot upload: " + json.dumps(res.get("bot") or res, ensure_ascii=False))
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Bot yuklenemedi")
            messagebox.showinfo("Tamam", "Bot servera yuklendi")
        except Exception as exc:
            self.log_line("Bot upload hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def generate_script(self):
        try:
            self.save_settings()
            client_id = "fmf_" + secrets.token_hex(8)
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
            lic_res = api_json("POST", self.server_url("/flash/admin/license/create"), payload, self.admin_var.get().strip())
            if not lic_res.get("success"):
                raise RuntimeError(lic_res.get("error") or "Lisans olusmadi")
            lic = lic_res["license"]
            server_url = self.server_var.get().strip().rstrip("/")
            host = urlparse(server_url).netloc
            script = (CLIENT_TEMPLATE
                      .replace("__CLIENT_NAME__", user_name)
                      .replace("__CLIENT_ID__", client_id)
                      .replace("__SCRIPT_ID__", script_id)
                      .replace("__SERVER_URL__", server_url)
                      .replace("__SERVER_HOST__", host))
            out_path = GENERATED_DIR / f"{safe_name(user_name)}_{client_id[:8]}.user.js"
            out_path.write_text(script, encoding="utf-8")
            index = load_json(SCRIPT_INDEX_FILE, {})
            index[str(lic.get("id") or "")] = str(out_path)
            save_json(SCRIPT_INDEX_FILE, index)
            self.log_line("Script uretildi: " + str(out_path))
            self.refresh_licenses(silent=True)
            self.license_name_var.set(self.next_user_name())
            self.license_key_var.set("")
            messagebox.showinfo("Tamam", f"Script hazir:\n{out_path}\n\nKullanici key ekraninda bu keyi girecek:\n{lic.get('key', '')}")
        except Exception as exc:
            self.log_line("Script hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def refresh_licenses(self, silent=False):
        try:
            res = api_json("GET", self.server_url("/flash/admin/licenses"), None, self.admin_var.get().strip())
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Liste alinamadi")
            self.licenses_cache = res.get("licenses") or []
            self.refresh_tree()
            if not silent:
                self.log_line(f"Lisans listesi yenilendi: {len(self.licenses_cache)}")
            current_name = self.license_name_var.get().strip()
            if not current_name or self.is_reserved_user_name(current_name):
                self.license_name_var.set(self.next_user_name())
        except Exception as exc:
            if not silent:
                self.log_line("Lisans liste hata: " + str(exc))

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
                "EVET" if lic.get("online") else "HAYIR",
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
            res = api_json("POST", self.server_url("/flash/admin/license/key"), {"license_id": lic.get("id", ""), "key": new_key}, self.admin_var.get().strip())
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
            res = api_json("POST", self.server_url("/flash/admin/license/toggle"), payload, self.admin_var.get().strip())
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Guncellenemedi")
            self.refresh_licenses(silent=True)
            self.log_line("Lisans guncellendi")
        except Exception as exc:
            self.log_line("Lisans guncelleme hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def delete_selected(self):
        try:
            lic = self.get_selected_license()
            if not lic:
                return
            if not messagebox.askyesno("Sil", f"{lic.get('name') or 'Lisans'} silinsin mi?"):
                return
            res = api_json("POST", self.server_url("/flash/admin/license/delete"), {"license_id": lic.get("id", "")}, self.admin_var.get().strip())
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Silinemedi")
            self.refresh_licenses(silent=True)
            self.log_line("Lisans silindi")
        except Exception as exc:
            self.log_line("Silme hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def health_check(self):
        try:
            res = api_json("GET", self.server_url("/flash/health"), None, "")
            self.log_line("Health: " + json.dumps(res, ensure_ascii=False))
            messagebox.showinfo("Health", json.dumps(res, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.log_line("Health hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def server_url(self, path: str) -> str:
        return self.server_var.get().strip().rstrip("/") + path

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
    FlashMinersPanel().mainloop()

