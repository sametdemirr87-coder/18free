const KEYS = {
  state: 'minerbytsfree_runtime',
  router: 'nexus_router_control',
  bot: {
    minerbyts: 'minerbytsfree_bot_bundle',
    zuncia: 'zuncia_bot_bundle',
    aztlacoin: 'aztlacoin_bot_bundle',
    cryptocrops: 'cryptocrops_bot_bundle',
    lightningminer: 'lightningminer_bot_bundle'
  },
  scripts: {
    cryptocrops: 'cryptocrops_script_packages',
    lightningminer: 'lightningminer_script_packages'
  }
};

const APPS = ['minerbyts', 'zuncia', 'aztlacoin', 'cryptocrops', 'lightningminer'];
const FAILOVER_STATUS = new Set([429, 500, 502, 503, 504]);
const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
};

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    const url = new URL(request.url);
    try {
      if (url.pathname.startsWith('/__router/')) return await routerAdmin(request, env);
      const control = await loadControl(env);
      if (control.mode !== 'secondary') {
        const secondaryRequest = request.clone();
        try {
          const upstream = await proxyPrimary(request, env);
          if (!FAILOVER_STATUS.has(upstream.status)) return withCors(upstream);
          await switchSecondary(env, `primary_http_${upstream.status}`);
        } catch (error) {
          await switchSecondary(env, `primary_fetch_${String(error && error.message || error).slice(0, 120)}`);
        }
        return withCors(await localApi(secondaryRequest, env));
      }
      return withCors(await localApi(request, env));
    } catch (error) {
      return json({ success: false, error: String(error && error.message || error) }, error instanceof HttpError ? error.status : 500);
    }
  }
};

async function proxyPrimary(request, env) {
  const incoming = new URL(request.url);
  const target = new URL(incoming.pathname + incoming.search, env.PRIMARY_ORIGIN);
  return fetch(new Request(target, request));
}

async function loadControl(env) {
  return (await readValue(env, KEYS.router)) || {
    mode: 'primary', primary_origin: env.PRIMARY_ORIGIN, switched_at: '', reason: ''
  };
}

async function switchSecondary(env, reason) {
  await writeValue(env, KEYS.router, {
    mode: 'secondary', primary_origin: env.PRIMARY_ORIGIN,
    switched_at: now(), reason
  });
}

async function routerAdmin(request, env) {
  requireAdmin(request, env);
  const url = new URL(request.url);
  if (request.method === 'GET' && url.pathname === '/__router/status') {
    return json({ success: true, ...(await loadControl(env)) });
  }
  if (request.method === 'POST' && url.pathname === '/__router/switch') {
    const body = await bodyJson(request);
    if (!['primary', 'secondary'].includes(body.mode)) return json({ success: false, error: 'mode primary veya secondary olmali' }, 400);
    const value = { mode: body.mode, primary_origin: env.PRIMARY_ORIGIN, switched_at: now(), reason: 'admin_switch' };
    await writeValue(env, KEYS.router, value);
    return json({ success: true, ...value });
  }
  return json({ success: false, error: 'Not found' }, 404);
}

async function localApi(request, env) {
  const url = new URL(request.url);
  const { app, path } = parseApp(url.pathname);
  if (request.method === 'GET' && path === '/') return json({ success: true, project: env.PROJECT_NAME || 'minerbytsfree', message: 'Nexus secondary active' });
  if (request.method === 'GET' && path === '/health') return health(env, app);
  if (request.method === 'POST' && path === '/api/auth') return auth(request, env, app);
  if (request.method === 'POST' && path === '/api/heartbeat') return heartbeat(request, env, app);
  if (request.method === 'POST' && path === '/api/tamper/report') return tamper(request, env, app);
  if (request.method === 'GET' && path === '/api/tamper/report.gif') return tamperGif(request, env, app);
  if (request.method === 'GET' && path === '/api/bot/bundle') return botBundle(request, env, app);
  if (request.method === 'GET' && path === '/admin/licenses') return adminLicenses(request, env, app);
  if (request.method === 'POST' && path === '/admin/license/create') return adminCreate(request, env, app);
  if (request.method === 'POST' && path === '/admin/license/toggle') return adminToggle(request, env, app);
  if (request.method === 'POST' && path === '/admin/license/key') return adminKey(request, env, app);
  if (request.method === 'POST' && path === '/admin/license/delete') return adminDelete(request, env, app);
  if (request.method === 'POST' && path === '/admin/license/tamper-clear') return adminTamperClear(request, env, app);
  if (request.method === 'POST' && path === '/admin/bot/upload') return adminBotUpload(request, env, app);
  if (request.method === 'POST' && path === '/admin/script/upload') return adminScriptUpload(request, env, app);
  const scriptMatch = path.match(/^\/script\/([^/]+)\.user\.js$/);
  if (request.method === 'GET' && scriptMatch) return serveScript(request, env, app, scriptMatch[1]);
  return json({ success: false, error: 'Not found' }, 404);
}

function parseApp(pathname) {
  for (const app of APPS.slice(1)) {
    const prefix = `/${app}`;
    if (pathname === prefix || pathname.startsWith(prefix + '/')) return { app, path: pathname.slice(prefix.length) || '/' };
  }
  return { app: 'minerbyts', path: pathname };
}

async function health(env, app) {
  const state = await loadState(env);
  const s = appState(state, app);
  const bundle = await readValue(env, KEYS.bot[app]) || {};
  return json({ success: true, project: app, status: 'ready', time: now(), supabase: true,
    license_count: s.licenses.length, bot_uploaded: !!bundle.content, bot_hash: bundle.hash || '', backend: 'cloudflare-secondary' });
}

async function auth(request, env, app) {
  const body = await bodyJson(request);
  const state = await loadState(env);
  const s = appState(state, app);
  const lic = s.licenses.find(x => String(x.key || '').trim() === String(body.license_key || '').trim());
  if (!lic) return json({ success: false, error: 'Lisans bulunamadi' });
  if (lic.tamper_detected) return json({ success: false, error: 'Connect Nexus.' });
  if (lic.active === false) return json({ success: false, error: 'Lisans pasif' });
  const binding = validateBinding(lic, body);
  if (binding) return json({ success: false, error: binding });
  lic.session_token = randomToken(); lic.online = true; lic.last_seen_at = now();
  lic.last_page = body.page || ''; lic.last_user_agent = body.user_agent || '';
  await saveState(env, state);
  const bundle = await readValue(env, KEYS.bot[app]) || {};
  return json({ success: true, token: lic.session_token, license: sanitize(lic), settings: s.settings,
    bot: summarize(bundle) });
}

async function heartbeat(request, env, app) {
  const body = await bodyJson(request);
  const state = await loadState(env); const s = appState(state, app);
  const lic = s.licenses.find(x => x.session_token && x.session_token === body.token);
  if (!lic) return json({ success: false, error: 'Oturum gecersiz' });
  if (lic.tamper_detected) return json({ success: false, error: 'Connect Nexus.' });
  const binding = validateBinding(lic, body);
  if (binding) return json({ success: false, error: binding });
  return json({ success: true, server_time: now(), settings: s.settings });
}

async function botBundle(request, env, app) {
  const url = new URL(request.url); const state = await loadState(env); const s = appState(state, app);
  const lic = s.licenses.find(x => x.session_token && x.session_token === url.searchParams.get('token'));
  if (!lic) return json({ success: false, error: 'Oturum gecersiz' });
  if (lic.tamper_detected) return json({ success: false, error: 'Connect Nexus.' });
  const body = { client_id: url.searchParams.get('client_id'), script_id: url.searchParams.get('script_id'), account_id: url.searchParams.get('account_id') };
  const binding = validateBinding(lic, body); if (binding) return json({ success: false, error: binding });
  const bundle = await readValue(env, KEYS.bot[app]) || {};
  if (!bundle.content) return json({ success: false, error: 'Bot henuz yuklenmedi' });
  return json({ success: true, name: bundle.name || 'bot.txt', version: bundle.version || 0,
    hash: bundle.hash || '', encoding: 'xor-base64', encrypted: xorBase64(bundle.content, body.client_id) });
}

async function tamper(request, env, app) {
  const body = await bodyJson(request);
  if (app === 'zuncia' && body.source !== 'loader_keydown_v2') return json({ success: true, ignored: true, reason: 'legacy_unverified_signal', loader_update_required: true });
  const state = await loadState(env); const s = appState(state, app);
  let lic = s.licenses.find(x => (body.token && x.session_token === body.token) || (body.license_key && x.key === body.license_key));
  if (!lic) lic = s.licenses.find(x => body.client_id && [x.client_id, x.allowed_client_id].includes(body.client_id));
  if (!lic) return json({ success: false, error: 'Lisans bulunamadi' });
  const report = { reason: String(body.reason || 'f12').slice(0, 80), source: String(body.source || 'client').slice(0, 80),
    client_id: String(body.client_id || '').slice(0, 160), script_id: String(body.script_id || '').slice(0, 160),
    account_id: String(body.account_id || '').slice(0, 160), page: String(body.page || '').slice(0, 500),
    user_agent: String(body.user_agent || '').slice(0, 500), reported_at: now() };
  lic.tamper_detected = true; lic.tamper_reason = report.reason; lic.tamper_at = report.reported_at;
  lic.tamper_report = report; lic.active = false; lic.online = false; lic.session_token = '';
  await saveState(env, state); return json({ success: true, locked: true });
}

async function tamperGif(request, env, app) {
  const url = new URL(request.url);
  const fake = new Request(request.url, { method: 'POST', headers: request.headers,
    body: JSON.stringify(Object.fromEntries(url.searchParams.entries())) });
  await tamper(fake, env, app);
  return new Response(Uint8Array.from([71,73,70,56,57,97,1,0,1,0,128,0,0,0,0,0,255,255,255,33,249,4,1,0,0,0,0,44,0,0,0,0,1,0,1,0,0,2,2,68,1,0,59]), { headers: { 'Content-Type': 'image/gif', ...CORS } });
}

async function adminLicenses(request, env, app) {
  requireAdmin(request, env); const state = await loadState(env);
  return json({ success: true, licenses: appState(state, app).licenses.map(sanitize) });
}

async function adminCreate(request, env, app) {
  requireAdmin(request, env); const body = await bodyJson(request); const state = await loadState(env); const s = appState(state, app);
  const key = String(body.key || '').trim() || generateKey(app);
  if (s.licenses.some(x => x.key === key)) return json({ success: false, error: 'Bu key zaten var' });
  if (body.allowed_client_id && s.licenses.some(x => x.allowed_client_id === body.allowed_client_id || x.client_id === body.allowed_client_id)) return json({ success: false, error: 'Bu script kimligi zaten var' });
  const lic = { id: randomHex(8), name: String(body.name || 'User').trim(), key, active: body.active !== false,
    multi_account: !!body.multi_account, account_id: '', client_id: '', script_id: '',
    allowed_client_id: String(body.allowed_client_id || '').trim(), session_token: '', online: false,
    created_at: now(), last_seen_at: '', last_page: '', tamper_detected: false, tamper_reason: '', tamper_at: '', tamper_report: {} };
  s.licenses.unshift(lic); await saveState(env, state); return json({ success: true, license: sanitize(lic) });
}

async function adminToggle(request, env, app) {
  requireAdmin(request, env); const body = await bodyJson(request); const [state, lic] = await findAdminLicense(env, app, body.license_id);
  if (!lic) return json({ success: false, error: 'Lisans bulunamadi' });
  if ('active' in body) { if (body.active && lic.tamper_detected) return json({ success: false, error: 'F12 damgasi temizlenmeden aktif edilemez' }); lic.active = !!body.active; }
  if ('multi_account' in body) lic.multi_account = !!body.multi_account; if (body.reset_account) lic.account_id = '';
  await saveState(env, state); return json({ success: true, license: sanitize(lic) });
}

async function adminKey(request, env, app) {
  requireAdmin(request, env); const body = await bodyJson(request); const [state, lic, s] = await findAdminLicense(env, app, body.license_id);
  const key = String(body.key || '').trim(); if (!lic) return json({ success: false, error: 'Lisans bulunamadi' });
  if (!key) return json({ success: false, error: 'Key bos olamaz' });
  if (s.licenses.some(x => x !== lic && x.key === key)) return json({ success: false, error: 'Bu key baska lisansta var' });
  lic.key = key; await saveState(env, state); return json({ success: true, license: sanitize(lic) });
}

async function adminDelete(request, env, app) {
  requireAdmin(request, env); const body = await bodyJson(request); const state = await loadState(env); const s = appState(state, app);
  const before = s.licenses.length; s.licenses = s.licenses.filter(x => x.id !== body.license_id);
  if (KEYS.scripts[app]) { const packages = await readValue(env, KEYS.scripts[app]) || {}; for (const [k,v] of Object.entries(packages)) if (v.license_id === body.license_id) delete packages[k]; await writeValue(env, KEYS.scripts[app], packages); }
  await saveState(env, state); return json({ success: true, deleted: before - s.licenses.length });
}

async function adminTamperClear(request, env, app) {
  requireAdmin(request, env); const body = await bodyJson(request); const [state, lic] = await findAdminLicense(env, app, body.license_id);
  if (!lic) return json({ success: false, error: 'Lisans bulunamadi' });
  Object.assign(lic, { tamper_detected:false, tamper_reason:'', tamper_at:'', tamper_report:{}, session_token:'', online:false });
  await saveState(env, state); return json({ success: true, license: sanitize(lic) });
}

async function adminBotUpload(request, env, app) {
  requireAdmin(request, env); const body = await bodyJson(request); if (!String(body.content || '').trim()) return json({ success:false, error:'Bot icerigi bos' });
  const old = await readValue(env, KEYS.bot[app]) || {}; const bundle = { name:body.file_name || 'bot.txt', content:String(body.content),
    hash:await sha256(String(body.content)), version:Number(old.version || 0) + 1, updated_at:now() };
  await writeValue(env, KEYS.bot[app], bundle); return json({ success:true, bot:summarize(bundle) });
}

async function adminScriptUpload(request, env, app) {
  requireAdmin(request, env); if (!KEYS.scripts[app]) return json({ success:false, error:'Bu uygulama script paketi desteklemiyor' }, 404);
  const body = await bodyJson(request); const packages = await readValue(env, KEYS.scripts[app]) || {};
  packages[body.script_id] = { license_id:String(body.license_id || ''), client_id:String(body.client_id || ''), content:String(body.content || ''), updated_at:now() };
  await writeValue(env, KEYS.scripts[app], packages); return json({ success:true, script_id:body.script_id });
}

async function serveScript(request, env, app, scriptId) {
  if (!KEYS.scripts[app]) return json({ success:false, error:'Script bulunamadi' }, 404);
  const packages = await readValue(env, KEYS.scripts[app]) || {}; const pkg = packages[scriptId] || {};
  const clientId = new URL(request.url).searchParams.get('client_id') || '';
  if (!pkg.content || String(pkg.client_id || '') !== clientId) return json({ success:false, error:'Script bulunamadi' }, 404);
  return new Response(pkg.content, { headers:{ 'Content-Type':'application/javascript; charset=utf-8', 'Cache-Control':'no-store', ...CORS } });
}

async function findAdminLicense(env, app, id) { const state = await loadState(env); const s = appState(state, app); return [state, s.licenses.find(x => x.id === id), s]; }

async function loadState(env) { const state = (await readValue(env, KEYS.state)) || {}; ensureState(state); return state; }
async function saveState(env, state) { await writeValue(env, KEYS.state, state); }

function ensureState(state) {
  state.project ||= 'minerbytsfree'; state.licenses ||= []; state.settings ||= { heartbeat_seconds:30, bind_mode:'first_account' };
  for (const app of APPS.slice(1)) { state[app] ||= {}; state[app].licenses ||= []; state[app].settings ||= { heartbeat_seconds:30, bind_mode:'first_account' }; }
}
function appState(state, app) { return app === 'minerbyts' ? state : state[app]; }

async function readValue(env, key) {
  const base = String(env.SUPABASE_URL || '').replace(/\/$/, ''); if (!base || !env.SUPABASE_SERVICE_KEY) throw new Error('Supabase secrets missing');
  const res = await fetch(`${base}/rest/v1/app_state?key=eq.${encodeURIComponent(key)}&select=value&limit=1`, { headers:supabaseHeaders(env) });
  if (!res.ok) throw new Error(`Supabase read ${res.status}`); const rows = await res.json(); return rows[0] && rows[0].value;
}
async function writeValue(env, key, value) {
  const base = String(env.SUPABASE_URL || '').replace(/\/$/, '');
  const res = await fetch(`${base}/rest/v1/app_state`, { method:'POST', headers:{ ...supabaseHeaders(env), 'Content-Type':'application/json', Prefer:'resolution=merge-duplicates,return=minimal' },
    body:JSON.stringify({ key, value, updated_at:now() }) }); if (!res.ok) throw new Error(`Supabase write ${res.status}`);
}
function supabaseHeaders(env) { return { apikey:env.SUPABASE_SERVICE_KEY, Authorization:`Bearer ${env.SUPABASE_SERVICE_KEY}` }; }

function validateBinding(lic, body) {
  const client = String(body.client_id || '').trim(), script = String(body.script_id || '').trim(), account = String(body.account_id || '').trim();
  if (!client) return 'Client ID eksik'; if (lic.allowed_client_id && lic.allowed_client_id !== client) return 'Bu script bu lisansa ait degil';
  lic.client_id ||= client; if (!lic.script_id && script) lic.script_id = script;
  if (lic.client_id !== client) return 'Client ID uyusmuyor'; if (lic.script_id && script && lic.script_id !== script) return 'Script ID uyusmuyor';
  if (account) { if (lic.multi_account) lic.last_account_id = account; else if (!lic.account_id) lic.account_id = account; else if (lic.account_id !== account) lic.last_account_id = account; }
  return null;
}

function sanitize(x) { return { id:x.id || '', name:x.name || '', key:x.key || '', active:x.active !== false, multi_account:!!x.multi_account,
  account_id:x.account_id || '', last_account_id:x.last_account_id || '', client_id:x.client_id || '', script_id:x.script_id || '',
  allowed_client_id:x.allowed_client_id || '', online:!!x.online, tamper_detected:!!x.tamper_detected, tamper_reason:x.tamper_reason || '',
  tamper_at:x.tamper_at || '', tamper_report:x.tamper_report || {}, created_at:x.created_at || '', last_seen_at:x.last_seen_at || '', last_page:x.last_page || '' }; }
function summarize(b) { return { name:b.name || '', hash:b.hash || '', version:b.version || 0, updated_at:b.updated_at || '', uploaded:!!b.content }; }
function requireAdmin(request, env) { if (!env.ADMIN_TOKEN || request.headers.get('X-Admin-Token') !== env.ADMIN_TOKEN) throw new HttpError(401, 'Unauthorized'); }
function generateKey(app) { const prefix = app === 'zuncia' ? 'ZNC' : app === 'aztlacoin' ? 'AZT' : app === 'lightningminer' ? 'NXL' : 'MBF'; return `${prefix}-${randomHex(2)}-${randomHex(2)}-${randomHex(2)}-${randomHex(2)}`.toUpperCase(); }
function randomHex(bytes) { const a = crypto.getRandomValues(new Uint8Array(bytes)); return [...a].map(x => x.toString(16).padStart(2,'0')).join(''); }
function randomToken() { const a = crypto.getRandomValues(new Uint8Array(32)); return btoa(String.fromCharCode(...a)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,''); }
async function sha256(text) { const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)); return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2,'0')).join(''); }
function xorBase64(text, keyText) { const p = new TextEncoder().encode(text), k = new TextEncoder().encode(keyText || 'minerbytsfree'), out = new Uint8Array(p.length); for (let i=0;i<p.length;i++) out[i] = p[i] ^ k[i % k.length]; let s=''; for (let i=0;i<out.length;i+=0x8000) s += String.fromCharCode(...out.subarray(i,i+0x8000)); return btoa(s); }
async function bodyJson(request) { try { return await request.json(); } catch { return {}; } }
function now() { return new Date().toISOString(); }
function json(data, status=200) { const actual = data && data.__status || status; return new Response(JSON.stringify(data), { status:actual, headers:{ 'Content-Type':'application/json; charset=utf-8', ...CORS } }); }
function withCors(response) { const h = new Headers(response.headers); for (const [k,v] of Object.entries(CORS)) h.set(k,v); return new Response(response.body, { status:response.status, statusText:response.statusText, headers:h }); }
class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }
