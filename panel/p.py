#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LightningMiner icin ayri lisans, script ve bot yonetim paneli."""

from __future__ import annotations

import secrets
from pathlib import Path
from tkinter import messagebox

import o as base_panel


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
SETTINGS_FILE = BASE_DIR / "lightningminer_panel_settings.json"
BOT_FILE = ROOT_DIR / "BotLig.txt"
GENERATED_DIR = BASE_DIR / "generated_lightningminer_scripts"
GENERATED_DIR.mkdir(exist_ok=True)
SCRIPT_INDEX_FILE = BASE_DIR / "generated_lightningminer_scripts_index.json"

DEFAULT_SETTINGS = {
    "server_url": "https://one8free.onrender.com",
    "admin_token": "MbfAdmin_18free!7429",
    "selected_bot_path": str(BOT_FILE),
}


CUBE_GATE = r'''    function showGate(message = '') {
        try {
            removeGate();
            const saved = getSavedLicenseKey();
            uiRoot = document.createElement('div');
            uiRoot.id = 'nexusFreeGate';
            uiRoot.innerHTML = `
                <style>
                    #nexusFreeGate{position:fixed;inset:0;z-index:2147483647;display:grid;place-items:center;overflow:hidden;font-family:Inter,Segoe UI,Arial,sans-serif;color:#eefaff;background:radial-gradient(circle at 50% 35%,#17336b66,transparent 28%),radial-gradient(circle at 15% 80%,#d946ef2e,transparent 30%),linear-gradient(145deg,#030611 0%,#080d22 48%,#02040c 100%);backdrop-filter:blur(18px)}
                    #nexusFreeGate:before{content:"";position:absolute;inset:-60%;background:conic-gradient(from 0deg,transparent,#22d3ee15,transparent,#d946ef15,transparent);animation:bgOrbit 16s linear infinite}
                    .nfg-shell{position:relative;width:min(760px,calc(100vw - 28px));height:480px;display:grid;place-items:center;perspective:1100px;animation:gateIn .75s cubic-bezier(.16,1,.3,1) both}
                    .cube-wrap{position:absolute;left:50%;top:44%;width:330px;height:210px;transform:translate(-50%,-50%);transform-style:preserve-3d;filter:drop-shadow(0 30px 35px #000b);animation:cubeIntro 2.65s cubic-bezier(.35,.05,.25,1) both}
                    .cube-half{position:absolute;top:0;width:156px;height:210px;display:grid;grid-template-columns:repeat(2,70px);grid-template-rows:repeat(3,62px);gap:8px;padding:8px;border:1px solid #ffffff38;border-radius:22px;background:#070b18dd;box-shadow:inset 0 0 28px #000,0 0 34px #22d3ee24;transform-style:preserve-3d;filter:brightness(.92);animation-duration:.9s;animation-delay:2.35s;animation-timing-function:cubic-bezier(.16,1,.3,1);animation-fill-mode:forwards}
                    .cube-half.left{left:9px;transform:translateX(0) rotateX(-8deg);animation-name:openLeft}
                    .cube-half.right{left:165px;transform:translateX(0) rotateX(-8deg);animation-name:openRight}
                    .tile{position:relative;border-radius:13px;border:2px solid #ffffff55;box-shadow:inset 0 5px 10px #ffffff38,inset 0 -8px 14px #0005,0 0 17px currentColor;animation:tilePulse 3.2s ease-in-out infinite}
                    .tile:nth-child(1){color:#22d3ee;background:#06b6d4}.tile:nth-child(2){color:#facc15;background:#eab308}.tile:nth-child(3){color:#f43f5e;background:#e11d48}.tile:nth-child(4){color:#a78bfa;background:#8b5cf6}.tile:nth-child(5){color:#4ade80;background:#22c55e}.tile:nth-child(6){color:#fb923c;background:#f97316}
                    .cube-half:before,.cube-half:after{content:"";position:absolute;pointer-events:none;border:1px solid #ffffff22;background:linear-gradient(135deg,#0e1838dd,#050713ee)}
                    .cube-half:before{left:18px;right:18px;height:34px;bottom:-28px;transform:rotateX(72deg);transform-origin:top;border-radius:0 0 13px 13px}
                    .cube-half:after{top:18px;bottom:18px;width:30px;right:-24px;transform:rotateY(72deg);transform-origin:left;border-radius:0 12px 12px 0}
                    .nfg-card{position:relative;z-index:4;width:min(340px,calc(100vw - 54px));padding:25px 26px 22px;border:1px solid #67e8f944;border-radius:24px;background:linear-gradient(155deg,#0d1732ed,#090c1bed);box-shadow:0 28px 90px #000c,0 0 60px #22d3ee20,inset 0 1px #ffffff14;backdrop-filter:blur(22px);opacity:0;transform:translateZ(-180px) scale(.42);filter:blur(12px);pointer-events:none;animation:panelReveal .72s 2.72s cubic-bezier(.16,1,.3,1) forwards}
                    .nfg-ready .nfg-card{pointer-events:auto;opacity:1;transform:translateZ(0) scale(1);filter:none;animation:none}
                    .nfg-kicker{text-align:center;color:#67e8f9;font-size:10px;font-weight:900;letter-spacing:3.4px;text-transform:uppercase}.nfg-title{margin:8px 0 5px;text-align:center;font-size:25px;font-weight:950;letter-spacing:.5px;background:linear-gradient(90deg,#67e8f9,#fff,#e879f9);-webkit-background-clip:text;color:transparent}.nfg-copy{text-align:center;color:#7f91b8;font-size:11px;margin-bottom:18px}
                    .nfg-field{position:relative}.nfg-input{width:100%;box-sizing:border-box;padding:15px 48px 15px 16px;border:1px solid #38bdf855;border-radius:14px;outline:none;background:#030713cc;color:#effcff;font-size:14px;font-weight:800;letter-spacing:1px;box-shadow:inset 0 0 20px #0008}.nfg-input:focus{border-color:#67e8f9;box-shadow:0 0 0 4px #22d3ee17,inset 0 0 20px #0008}.nfg-keydot{position:absolute;right:15px;top:50%;width:12px;height:12px;border-radius:4px;background:linear-gradient(135deg,#22d3ee,#d946ef);transform:translateY(-50%) rotate(45deg);box-shadow:0 0 18px #22d3ee}
                    .nfg-btn{width:100%;margin-top:12px;padding:14px;border:0;border-radius:14px;color:#06101c;background:linear-gradient(100deg,#22d3ee,#67e8f9 48%,#d8b4fe);font-size:12px;font-weight:950;letter-spacing:1.8px;cursor:pointer;box-shadow:0 16px 38px #22d3ee32;transition:.2s}.nfg-btn:hover{transform:translateY(-2px);filter:brightness(1.08)}
                    .nfg-status{min-height:18px;margin-top:12px;text-align:center;color:#9db1d7;font-size:11px;font-weight:800}.nfg-loader{display:none;width:28px;height:28px;margin:13px auto 0;border:3px solid #22d3ee25;border-top-color:#67e8f9;border-radius:50%;animation:spin .7s linear infinite}.nfg-loading .nfg-loader{display:block}.nfg-loading .nfg-btn,.nfg-loading .nfg-input{opacity:.45;pointer-events:none}
                    .nfg-error .nfg-card{animation:wrongKey .48s cubic-bezier(.36,.07,.19,.97)}.nfg-error .cube-half{filter:drop-shadow(0 0 28px #fb395f)}
                    .nfg-success .nfg-card{animation:panelRetract .48s cubic-bezier(.7,0,1,.3) forwards;pointer-events:none}.nfg-success .cube-half.left{animation:closeLeft .72s .28s cubic-bezier(.7,0,.2,1) forwards}.nfg-success .cube-half.right{animation:closeRight .72s .28s cubic-bezier(.7,0,.2,1) forwards}.nfg-success .cube-wrap{animation:flyCore 1.5s .92s cubic-bezier(.55,.02,.8,.2) forwards}.nfg-success{animation:gateOut .42s ease 2.18s forwards}
                    @keyframes cubeIntro{0%{transform:translate(-50%,-50%) rotateX(-18deg) rotateY(0deg) scale(.72);filter:brightness(.45) blur(6px)}18%{filter:brightness(1.2) blur(0)}100%{transform:translate(-50%,-50%) rotateX(-8deg) rotateY(360deg) scale(1);filter:brightness(1)}}
                    @keyframes openLeft{to{transform:translateX(-220px) rotateX(-12deg) rotateY(28deg);filter:brightness(1)}}@keyframes openRight{to{transform:translateX(220px) rotateX(-12deg) rotateY(-28deg);filter:brightness(1)}}
                    @keyframes panelReveal{0%{opacity:0;transform:translateZ(-180px) scale(.42);filter:blur(12px)}100%{opacity:1;transform:translateZ(0) scale(1);filter:none}}
                    @keyframes panelRetract{to{opacity:0;transform:translateZ(-190px) scale(.28);filter:blur(14px)}}@keyframes closeLeft{from{transform:translateX(-220px) rotateX(-12deg) rotateY(28deg)}to{transform:translateX(0) rotateX(-8deg) rotateY(0)}}@keyframes closeRight{from{transform:translateX(220px) rotateX(-12deg) rotateY(-28deg)}to{transform:translateX(0) rotateX(-8deg) rotateY(0)}}
                    @keyframes flyCore{0%{transform:translate(-50%,-50%) rotateX(-8deg) rotateY(360deg) scale(1);opacity:1}35%{transform:translate(-50%,-62%) rotateX(110deg) rotateY(620deg) scale(.9);opacity:1}100%{transform:translate(-50%,-260%) rotateX(520deg) rotateY(1180deg) scale(.08);opacity:0;filter:blur(9px)}}
                    @keyframes wrongKey{10%,90%{transform:translateX(-2px)}20%,80%{transform:translateX(7px)}30%,50%,70%{transform:translateX(-11px)}40%,60%{transform:translateX(11px)}}@keyframes tilePulse{50%{filter:saturate(1.5) brightness(1.16)}}@keyframes spin{to{transform:rotate(360deg)}}@keyframes bgOrbit{to{transform:rotate(360deg)}}@keyframes gateIn{from{opacity:0;transform:scale(1.08);filter:blur(14px)}to{opacity:1;transform:none;filter:none}}@keyframes gateOut{to{opacity:0;filter:blur(18px)}}
                    @media(max-width:680px){.nfg-shell{height:520px}.cube-wrap{top:37%;animation-name:cubeIntroMobile}.nfg-card{margin-top:180px}.cube-half.left{animation-name:openLeftMobile}.cube-half.right{animation-name:openRightMobile}.nfg-success .cube-half.left{animation-name:closeLeftMobile}.nfg-success .cube-half.right{animation-name:closeRightMobile}.nfg-success .cube-wrap{animation-name:flyCoreMobile}@keyframes cubeIntroMobile{0%{transform:translate(-50%,-50%) rotateX(-18deg) rotateY(0) scale(.55);filter:brightness(.45) blur(6px)}100%{transform:translate(-50%,-50%) rotateX(-8deg) rotateY(360deg) scale(.74);filter:brightness(1)}}@keyframes openLeftMobile{to{transform:translateX(-132px) rotateY(18deg)}}@keyframes openRightMobile{to{transform:translateX(132px) rotateY(-18deg)}}@keyframes closeLeftMobile{from{transform:translateX(-132px) rotateY(18deg)}to{transform:translateX(0) rotateY(0)}}@keyframes closeRightMobile{from{transform:translateX(132px) rotateY(-18deg)}to{transform:translateX(0) rotateY(0)}}@keyframes flyCoreMobile{0%{transform:translate(-50%,-50%) rotateY(360deg) scale(.74);opacity:1}100%{transform:translate(-50%,-260%) rotateX(520deg) rotateY(1180deg) scale(.06);opacity:0;filter:blur(9px)}}}
                    @media(prefers-reduced-motion:reduce){.tile,#nexusFreeGate:before{animation:none}}
                </style>
                <div class="nfg-shell">
                    <div class="cube-wrap" aria-hidden="true">
                        <div class="cube-half left">${'<i class="tile"></i>'.repeat(6)}</div>
                        <div class="cube-half right">${'<i class="tile"></i>'.repeat(6)}</div>
                    </div>
                    <div class="nfg-card">
                        <div class="nfg-kicker">Nexus secure core</div>
                        <div class="nfg-title">LightningMind Cube</div>
                        <div class="nfg-copy">Akil kupunu birlestirmek icin lisans anahtarini gir.</div>
                        <div class="nfg-field"><input class="nfg-input" id="nfgKey" placeholder="NXL-XXXX-XXXX-XXXX-XXXX" value="${escapeAttr(saved)}" autocomplete="off" spellcheck="false"><span class="nfg-keydot"></span></div>
                        <button class="nfg-btn" id="nfgUnlock">KUPU BIRLESTIR</button>
                        <div class="nfg-loader"></div>
                        <div class="nfg-status" id="nfgStatus">${escapeHtml(message || 'Anahtar bekleniyor...')}</div>
                    </div>
                </div>`;
            document.documentElement.appendChild(uiRoot);
            setTimeout(() => { if (uiRoot) uiRoot.classList.add('nfg-ready'); }, 3450);
            document.getElementById('nfgUnlock').onclick = async () => {
                const key = String(document.getElementById('nfgKey').value || '').trim();
                if (!key) { setGateStatus('Lutfen lisans anahtarini gir.', true); return; }
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
        if (status) { status.textContent = text || ''; status.style.color = bad ? '#fb7185' : '#9db1d7'; }
        if (bad && uiRoot) {
            uiRoot.classList.remove('nfg-error');
            void uiRoot.offsetWidth;
            uiRoot.classList.add('nfg-error');
            setTimeout(() => uiRoot && uiRoot.classList.remove('nfg-error'), 560);
        }
    }

    function showGateSuccess() {
        return new Promise((resolve) => {
            if (!uiRoot) return resolve();
            uiRoot.classList.add('nfg-success');
            setGateStatus('Anahtar dogru. Bot baslatiliyor...', false);
            setTimeout(resolve, 2650);
        });
    }

'''


def build_client_template() -> str:
    source = base_panel.CLIENT_TEMPLATE
    replacements = {
        "nexus.cryptocrops.ultra": "nexus.lightningminer.secure",
        "Nexus CryptoCrops Ultra secure loader": "Nexus LightningMiner secure cube loader",
        "https://cryptocrops.net/*": "https://lightningminer.com/*",
        "/cryptocrops/script/": "/lightningminer/script/",
        "const API_PREFIX = '/cryptocrops';": "const API_PREFIX = '/lightningminer';",
        "cryptocrops_ultra_auth_": "lightningminer_auth_",
        "cryptocrops_ultra_auth_latest": "lightningminer_auth_latest",
        "cryptocrops_ultra_license_key_": "lightningminer_license_key_",
        "cryptocrops_ultra_device_id": "lightningminer_device_id",
        "__NEXUS_CROPCROPS_ULTRA_START__": "__NEXUS_LIGHTNINGMINER_START__",
        "cryptocrops_loader_keydown_v1": "lightningminer_loader_keydown_v1",
        "Loading Nexus Free Bot...": "Loading Nexus LightningMiner Bot...",
    }
    for old, new in replacements.items():
        source = source.replace(old, new)
    gate_start = source.index("    function showGate(")
    gate_end = source.index("    function removeGate()", gate_start)
    source = source[:gate_start] + CUBE_GATE + source[gate_end:]
    return source


def embed_lightning_bot(source: str) -> str:
    """Botu o.py ile ayni sekilde, key dogrulanana kadar bekleterek gom."""
    import re

    pattern = re.compile(r"\(\s*function\s*\(\s*\)\s*\{")
    if not pattern.search(source):
        raise RuntimeError("Bot baslangic yapisi bulunamadi")
    return pattern.sub(
        "(async function(){ await globalThis.__NEXUS_LIGHTNINGMINER_START__;",
        source,
        count=1,
    )


# Taban panelin ortak, denenmis yonetim kodunu LightningMiner ayarlariyla kullan.
base_panel.SETTINGS_FILE = SETTINGS_FILE
base_panel.BOT_FILE = BOT_FILE
base_panel.GENERATED_DIR = GENERATED_DIR
base_panel.SCRIPT_INDEX_FILE = SCRIPT_INDEX_FILE
base_panel.DEFAULT_SETTINGS = DEFAULT_SETTINGS
base_panel.CLIENT_TEMPLATE = build_client_template()
base_panel.embed_bot_for_loader = embed_lightning_bot


class LightningMinerPanel(base_panel.CryptoCropsUltraPanel):
    def __init__(self):
        super().__init__()
        self.title("LightningMiner Nexus Panel")
        self._rebrand_widgets(self)

    def _rebrand_widgets(self, widget):
        try:
            text = widget.cget("text")
            if isinstance(text, str):
                replacements = {
                    "🌾  NEXUS CROPCROPS ULTRA": "⚡  NEXUS LIGHTNINGMINER",
                    "ÇİFTLİK OTOMASYONU · LİSANS MERKEZİ": "LIGHTNINGMIND CUBE · LİSANS MERKEZİ",
                    "Hasat Lisansları": "Lightning Lisansları",
                    "🌱 Bot Tohumu": "⚡ Lightning Bot",
                    "🔑 Ultra Script Üret": "🧊 3D Küp Script Üret",
                    "Çiftlik sahibi": "Kullanıcı adı",
                    "🌾 Key + Script Üret": "🧊 Key + Script Üret",
                }
                widget.configure(text=replacements.get(text, text))
        except Exception:
            pass
        for child in widget.winfo_children():
            self._rebrand_widgets(child)

    def server_url(self, path: str) -> str:
        return self.server_var.get().strip().rstrip("/") + "/lightningminer" + path

    def generate_script(self):
        try:
            self.save_settings()
            bot_path = Path(self.bot_path_var.get().strip())
            if not bot_path.is_file():
                raise RuntimeError("Bot dosyasi bulunamadi")
            content = bot_path.read_text(encoding="utf-8", errors="replace")
            if not content.strip():
                raise RuntimeError("Bot dosyasi bos")
            base_panel.validate_bot_source(content)
            client_id = "lmn_" + secrets.token_hex(8)
            script_id = "script_" + secrets.token_hex(8)
            user_name = self.license_name_var.get().strip() or self.next_user_name()
            if self.is_reserved_user_name(user_name):
                user_name = self.next_user_name()
                self.license_name_var.set(user_name)
            payload = {
                "name": user_name,
                "active": True,
                "multi_account": bool(self.multi_var.get()),
                "allowed_client_id": client_id,
            }
            manual_key = self.license_key_var.get().strip()
            if manual_key:
                payload["key"] = manual_key
            lic_res = base_panel.api_json("POST", self.server_url("/admin/license/create"), payload, self.admin_var.get().strip())
            if not lic_res.get("success"):
                raise RuntimeError(lic_res.get("error") or "Lisans olusmadi")
            lic = lic_res["license"]
            server_url = self.server_var.get().strip().rstrip("/")
            script = base_panel.render_client_script(user_name, client_id, script_id, server_url, content)
            out_path = GENERATED_DIR / f"{base_panel.safe_name(user_name)}_{client_id[:8]}.user.js"
            out_path.write_text(script, encoding="utf-8")
            index = base_panel.load_json(SCRIPT_INDEX_FILE, {})
            index[str(lic.get("id") or "")] = str(out_path)
            base_panel.save_json(SCRIPT_INDEX_FILE, index)
            self.publish_script_package(str(lic.get("id") or ""), client_id, script_id, script)
            self.log_line("LightningMiner script uretildi: " + str(out_path))
            self.refresh_licenses(silent=True)
            self.license_name_var.set(self.next_user_name())
            self.license_key_var.set("")
            messagebox.showinfo("Tamam", f"Script hazir:\n{out_path}\n\nKullanici kup ekraninda bu keyi girecek:\n{lic.get('key', '')}")
        except Exception as exc:
            self.log_line("Script hata: " + str(exc))
            messagebox.showerror("Hata", str(exc))


if __name__ == "__main__":
    LightningMinerPanel().mainloop()
