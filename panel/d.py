#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import secrets
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
SETTINGS_FILE = BASE_DIR / "panel_settings.json"
BOT_FILE = ROOT_DIR / "botfree.txt"
GENERATED_DIR = BASE_DIR / "generated_scripts"
GENERATED_DIR.mkdir(exist_ok=True)
SCRIPT_INDEX_FILE = BASE_DIR / "generated_scripts_index.json"

DEFAULT_SETTINGS = {
    "server_url": "https://your-render-app.onrender.com",
    "admin_token": "",
    "selected_bot_path": str(BOT_FILE),
}

CLIENT_TEMPLATE = r'''// ==UserScript==
// @name         __CLIENT_NAME__
// @namespace    minerbytsfree
// @version      1.0.0
// @description  MinerByts server lisansli bot yukleyici
// @match        https://minerbyts.com/games*
// @match        https://minerbyts.com/ptc*
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
    const STORAGE_KEY = 'minerbytsfree_auth_' + CLIENT_ID;
    const LICENSE_KEY = '__LICENSE_KEY__';
    let sessionToken = '';
    let loadedBotHash = '';
    let heartbeatTimer = null;

    function gmRequest(method, url, body) {
        return new Promise((resolve) => {
            GM_xmlhttpRequest({
                method,
                url,
                timeout: 15000,
                headers: { 'Content-Type': 'application/json' },
                data: body ? JSON.stringify(body) : undefined,
                onload: (res) => {
                    try {
                        const parsed = JSON.parse(res.responseText || '{}');
                        if (res.status >= 400 && parsed && !parsed.error) parsed.error = 'HTTP ' + res.status;
                        resolve(parsed);
                    } catch(e) {
                        resolve({ success:false, error:'Bozuk server yaniti', status:res.status || 0 });
                    }
                },
                onerror: () => resolve({ success:false, error:'Baglanti hatasi' }),
                ontimeout: () => resolve({ success:false, error:'Zaman asimi' })
            });
        });
    }

    function gmGet(url) {
        return new Promise((resolve) => {
            GM_xmlhttpRequest({
                method: 'GET',
                url,
                timeout: 15000,
                onload: (res) => {
                    try { resolve(JSON.parse(res.responseText || '{}')); }
                    catch(e) { resolve({ success:false, error:'Bozuk server yaniti' }); }
                },
                onerror: () => resolve({ success:false, error:'Baglanti hatasi' }),
                ontimeout: () => resolve({ success:false, error:'Zaman asimi' })
            });
        });
    }

    function apiUrl(path) {
        return String(SERVER_URL || '').replace(/\/$/, '') + path;
    }

    function saveAuth(payload) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(payload || {})); } catch(e) {}
        try { GM_setValue(STORAGE_KEY, JSON.stringify(payload || {})); } catch(e) {}
    }

    function loadAuth() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY) || GM_getValue(STORAGE_KEY) || '';
            return raw ? JSON.parse(raw) : {};
        } catch(e) { return {}; }
    }

    function collectAccountId() {
        const candidates = [];
        const push = (value) => {
            value = String(value || '').trim();
            if (value && !candidates.includes(value)) candidates.push(value);
        };
        try {
            ['user_id', 'userId', 'account_id', 'accountId', 'minerbyts_user'].forEach((key) => {
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
            let fp = localStorage.getItem('minerbytsfree_device_id') || '';
            if (!fp) {
                fp = 'dev_' + Math.random().toString(16).slice(2) + Date.now().toString(16);
                localStorage.setItem('minerbytsfree_device_id', fp);
            }
            return fp;
        } catch(e) {
            return CLIENT_ID;
        }
    }

    function log(text, bad = false) {
        try {
            let box = document.getElementById('mbfLoaderLog');
            if (!box) {
                box = document.createElement('div');
                box.id = 'mbfLoaderLog';
                box.style.cssText = 'position:fixed;left:14px;bottom:14px;z-index:2147483647;background:rgba(8,10,16,.92);color:#dbeafe;border:1px solid rgba(96,165,250,.35);border-radius:10px;padding:10px 12px;font:12px monospace;max-width:360px;box-shadow:0 12px 35px rgba(0,0,0,.35);';
                document.body.appendChild(box);
            }
            box.textContent = '[MinerBytsFree] ' + text;
            box.style.borderColor = bad ? 'rgba(248,113,113,.55)' : 'rgba(96,165,250,.35)';
        } catch(e) {}
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

    async function authenticate() {
        const stored = loadAuth();
        const licenseKey = String(stored.license_key || LICENSE_KEY || '').trim() || prompt('MinerBytsFree lisans key:');
        if (!licenseKey) return { success:false, error:'Lisans key yok' };
        const accountId = collectAccountId();
        const res = await gmRequest('POST', apiUrl('/api/auth'), {
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
        const res = await gmRequest('POST', apiUrl('/api/heartbeat'), {
            token: sessionToken,
            client_id: CLIENT_ID,
            script_id: SCRIPT_ID,
            account_id: collectAccountId(),
            page: location.href
        });
        if (!res || !res.success) {
            log((res && res.error) || 'Oturum kapandi', true);
            sessionToken = '';
            if (heartbeatTimer) clearInterval(heartbeatTimer);
        }
    }

    async function fetchAndRunBot() {
        const qs = '?token=' + encodeURIComponent(sessionToken)
            + '&client_id=' + encodeURIComponent(CLIENT_ID)
            + '&script_id=' + encodeURIComponent(SCRIPT_ID)
            + '&account_id=' + encodeURIComponent(collectAccountId());
        const bundle = await gmGet(apiUrl('/api/bot/bundle') + qs);
        if (!bundle || !bundle.success) {
            log((bundle && bundle.error) || 'Bot cekilemedi', true);
            return;
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
        log('Bot yuklendi: ' + (bundle.name || 'botfree.txt'));
        (0, eval)(code);
    }

    async function boot() {
        log('Lisans kontrol ediliyor...');
        const auth = await authenticate();
        if (!auth || !auth.success) {
            log((auth && auth.error) || 'Lisans girisi basarisiz', true);
            return;
        }
        await fetchAndRunBot();
        if (heartbeatTimer) clearInterval(heartbeatTimer);
        heartbeatTimer = setInterval(heartbeat, 30000);
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


class MinerBytsPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MinerBytsFree Server Panel")
        self.geometry("1080x720")
        self.minsize(980, 640)
        self.configure(bg="#0b1020")
        self.settings = {**DEFAULT_SETTINGS, **load_json(SETTINGS_FILE, {})}
        self.licenses_cache = []
        self.server_var = tk.StringVar(value=self.settings.get("server_url", ""))
        self.admin_var = tk.StringVar(value=self.settings.get("admin_token", ""))
        self.bot_path_var = tk.StringVar(value=self.settings.get("selected_bot_path", str(BOT_FILE)))
        self.license_name_var = tk.StringVar(value="User1")
        self.multi_var = tk.BooleanVar(value=False)
        self.tree_menu = None
        self.build_ui()
        self.refresh_licenses(silent=True)

    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background="#111827", foreground="#e5e7eb", fieldbackground="#111827", rowheight=28)
        style.configure("Treeview.Heading", background="#1f2937", foreground="#f9fafb", font=("Segoe UI", 10, "bold"))

        top = tk.Frame(self, bg="#0b1020")
        top.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(top, text="Server URL", bg="#0b1020", fg="#93c5fd").grid(row=0, column=0, sticky="w")
        tk.Entry(top, textvariable=self.server_var, bg="#111827", fg="#f8fafc", insertbackground="#f8fafc", relief="flat").grid(row=1, column=0, sticky="ew", padx=(0, 10), ipady=7)
        tk.Label(top, text="Admin Token", bg="#0b1020", fg="#93c5fd").grid(row=0, column=1, sticky="w")
        tk.Entry(top, textvariable=self.admin_var, bg="#111827", fg="#f8fafc", insertbackground="#f8fafc", relief="flat", show="*").grid(row=1, column=1, sticky="ew", padx=(0, 10), ipady=7)
        tk.Button(top, text="Kaydet", command=self.save_settings, bg="#2563eb", fg="white", relief="flat", padx=16).grid(row=1, column=2, sticky="ew")
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=2)

        botbar = tk.Frame(self, bg="#0b1020")
        botbar.pack(fill="x", padx=14, pady=8)
        tk.Entry(botbar, textvariable=self.bot_path_var, bg="#111827", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat").pack(side="left", fill="x", expand=True, ipady=7)
        tk.Button(botbar, text="Bot Sec", command=self.choose_bot, bg="#334155", fg="white", relief="flat", padx=14).pack(side="left", padx=8)
        tk.Button(botbar, text="Botu Servera Yukle", command=self.upload_bot, bg="#16a34a", fg="white", relief="flat", padx=14).pack(side="left")

        main = tk.Frame(self, bg="#0b1020")
        main.pack(fill="both", expand=True, padx=14, pady=8)

        left = tk.Frame(main, bg="#0b1020")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(main, bg="#0b1020", width=330)
        right.pack(side="right", fill="y", padx=(12, 0))

        create_box = tk.LabelFrame(left, text="Script Uret", bg="#0b1020", fg="#93c5fd", bd=1, relief="solid")
        create_box.pack(fill="x", pady=(0, 10))
        tk.Entry(create_box, textvariable=self.license_name_var, bg="#111827", fg="#f8fafc", insertbackground="#f8fafc", relief="flat").pack(side="left", fill="x", expand=True, padx=10, pady=10, ipady=7)
        tk.Checkbutton(create_box, text="Coklu hesap", variable=self.multi_var, bg="#0b1020", fg="#dbeafe", selectcolor="#111827", activebackground="#0b1020", activeforeground="#ffffff").pack(side="left", padx=8)
        tk.Button(create_box, text="Key + Script Uret", command=self.generate_script, bg="#7c3aed", fg="white", relief="flat", padx=14).pack(side="left", padx=10)

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

        actions = tk.Frame(right, bg="#0b1020")
        actions.pack(fill="x")
        tk.Button(actions, text="Lisanslari Yenile", command=self.refresh_licenses, bg="#2563eb", fg="white", relief="flat").pack(fill="x", pady=(0, 8), ipady=8)
        tk.Button(actions, text="Health Kontrol", command=self.health_check, bg="#334155", fg="white", relief="flat").pack(fill="x", pady=(0, 8), ipady=8)

        self.details = scrolledtext.ScrolledText(right, height=18, bg="#111827", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat", font=("Consolas", 9))
        self.details.pack(fill="both", expand=True, pady=(4, 10))
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
            res = api_json("POST", self.server_url("/admin/bot/upload"), {"file_name": path.name, "content": content}, self.admin_var.get().strip())
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
            client_id = "mbf_" + secrets.token_hex(8)
            script_id = "script_" + secrets.token_hex(8)
            user_name = self.license_name_var.get().strip() or self.next_user_name()
            lic_res = api_json("POST", self.server_url("/admin/license/create"), {
                "name": user_name,
                "active": True,
                "multi_account": bool(self.multi_var.get()),
                "allowed_client_id": client_id,
            }, self.admin_var.get().strip())
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
                      .replace("__SERVER_HOST__", host)
                      .replace("__LICENSE_KEY__", lic.get("key", "")))
            out_path = GENERATED_DIR / f"{safe_name(user_name)}_{client_id[:8]}.user.js"
            out_path.write_text(script, encoding="utf-8")
            index = load_json(SCRIPT_INDEX_FILE, {})
            index[str(lic.get("id") or "")] = str(out_path)
            save_json(SCRIPT_INDEX_FILE, index)
            self.log_line("Script uretildi: " + str(out_path))
            self.refresh_licenses(silent=True)
            self.license_name_var.set(self.next_user_name())
            messagebox.showinfo("Tamam", f"Script hazir:\n{out_path}\n\nKey:\n{lic.get('key', '')}")
        except Exception as exc:
            self.log_line("Script hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))

    def refresh_licenses(self, silent=False):
        try:
            res = api_json("GET", self.server_url("/admin/licenses"), None, self.admin_var.get().strip())
            if not res.get("success"):
                raise RuntimeError(res.get("error") or "Liste alinamadi")
            self.licenses_cache = res.get("licenses") or []
            self.refresh_tree()
            if not silent:
                self.log_line(f"Lisans listesi yenilendi: {len(self.licenses_cache)}")
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
            self.refresh_licenses(silent=True)
            self.log_line("Lisans silindi")
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

    def server_url(self, path: str) -> str:
        return self.server_var.get().strip().rstrip("/") + path

    def next_user_name(self) -> str:
        used = set()
        for lic in self.licenses_cache:
            name = str(lic.get("name") or "")
            if name.lower().startswith("user") and name[4:].isdigit():
                used.add(int(name[4:]))
        idx = 1
        while idx in used:
            idx += 1
        return f"User{idx}"

    def log_line(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")


if __name__ == "__main__":
    MinerBytsPanel().mainloop()
