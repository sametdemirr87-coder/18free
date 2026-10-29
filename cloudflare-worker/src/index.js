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
      // Telegram CAPTCHA relay is owned by the Cloudflare secondary. Keep these
      // routes local even while the primary API is active, otherwise an older
      // Render deployment can answer with 404 before failover is considered.
      if (request.method === 'POST' && url.pathname === '/cryptocrops/api/telegram/register') return withCors(await telegramRegister(request, env));
      if (request.method === 'POST' && url.pathname === '/cryptocrops/api/telegram/captcha/create') return withCors(await telegramCaptchaCreate(request, env));
      if (request.method === 'GET' && url.pathname === '/cryptocrops/api/telegram/captcha/status') return withCors(await telegramCaptchaStatus(request, env));
      if (request.method === 'POST' && url.pathname === '/cryptocrops/api/telegram/captcha/solve') return withCors(await telegramCaptchaSolve(request, env));
      if (request.method === 'POST' && url.pathname === '/cryptocrops/api/telegram/captcha/ack') return withCors(await telegramCaptchaAck(request, env));
      if (request.method === 'POST' && url.pathname === '/cryptocrops/api/telegram/captcha/retry') return withCors(await telegramCaptchaRetry(request, env));
      const directCaptchaProgress = url.pathname.match(/^\/cryptocrops\/api\/telegram\/captcha\/progress\/([A-Za-z0-9_-]+)$/);
      if (request.method === 'GET' && directCaptchaProgress) return withCors(await telegramCaptchaProgress(env, directCaptchaProgress[1]));
      const directCaptcha = url.pathname.match(/^\/cryptocrops\/telegram\/captcha\/([A-Za-z0-9_-]+)$/);
      if (request.method === 'GET' && directCaptcha) return withCors(await telegramCaptchaPage(env, directCaptcha[1]));
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
  if (app === 'cryptocrops' && request.method === 'POST' && path === '/api/telegram/register') return telegramRegister(request, env);
  if (app === 'cryptocrops' && request.method === 'POST' && path === '/api/telegram/captcha/create') return telegramCaptchaCreate(request, env);
  if (app === 'cryptocrops' && request.method === 'GET' && path === '/api/telegram/captcha/status') return telegramCaptchaStatus(request, env);
  if (app === 'cryptocrops' && request.method === 'POST' && path === '/api/telegram/captcha/solve') return telegramCaptchaSolve(request, env);
  if (app === 'cryptocrops' && request.method === 'POST' && path === '/api/telegram/captcha/ack') return telegramCaptchaAck(request, env);
  if (app === 'cryptocrops' && request.method === 'POST' && path === '/api/telegram/captcha/retry') return telegramCaptchaRetry(request, env);
  const telegramCaptchaProgressMatch = app === 'cryptocrops' && path.match(/^\/api\/telegram\/captcha\/progress\/([A-Za-z0-9_-]+)$/);
  if (request.method === 'GET' && telegramCaptchaProgressMatch) return telegramCaptchaProgress(env, telegramCaptchaProgressMatch[1]);
  const telegramCaptchaMatch = app === 'cryptocrops' && path.match(/^\/telegram\/captcha\/([A-Za-z0-9_-]+)$/);
  if (request.method === 'GET' && telegramCaptchaMatch) return telegramCaptchaPage(env, telegramCaptchaMatch[1]);
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
    license_count: s.licenses.length, bot_uploaded: !!bundle.content, bot_hash: bundle.hash || '', backend: 'cloudflare-secondary',
    captcha_link_mode: app === 'cryptocrops' ? 'isolated-session-v5' : undefined });
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

function requireCryptoRuntime(state, body) {
  const s = appState(state, 'cryptocrops');
  const token = String(body.token || '');
  const licenseKey = String(body.license_key || '').trim();
  const lic = s.licenses.find(x => (x.session_token && x.session_token === token) || (licenseKey && x.key === licenseKey));
  if (!lic || lic.active === false || lic.tamper_detected) throw new HttpError(403, 'Oturum gecersiz');
  const binding = validateBinding(lic, body);
  if (binding) throw new HttpError(403, binding);
  return lic;
}

async function telegramApi(token, method, payload) {
  token = String(token || '').trim();
  if (!token) return { ok:false, error:'Telegram bot token bos' };
  try {
    const response = await fetch(`https://api.telegram.org/bot${encodeURIComponent(token)}/${method}`, {
      method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify(payload || {})
    });
    const data = await response.json().catch(() => ({}));
    return { ok:response.ok && data.ok === true, data };
  } catch (error) {
    return { ok:false, error:String(error && error.message || error) };
  }
}

const CAPTCHA_SESSION_PREFIX = 'cryptocrops_captcha_';
const CAPTCHA_SESSION_TTL_MS = 30 * 60 * 1000;

function captchaSessionKey(captchaId) {
  const safe = String(captchaId || '').replace(/[^A-Za-z0-9_-]/g, '');
  return safe ? CAPTCHA_SESSION_PREFIX + safe : '';
}

async function readTelegramCaptcha(env, captchaId) {
  const key = captchaSessionKey(captchaId);
  if (!key) return null;
  const session = await readValue(env, key);
  if (!session || !session.captcha_id) return null;
  if (Date.now() - Number(session.created_epoch || 0) > CAPTCHA_SESSION_TTL_MS) {
    await writeValue(env, key, null);
    return null;
  }
  return session;
}

async function writeTelegramCaptcha(env, session) {
  const key = captchaSessionKey(session && session.captcha_id);
  if (!key) throw new Error('CAPTCHA oturum kimligi gecersiz');
  await writeValue(env, key, session);
}

async function telegramRegister(request, env) {
  const body = await bodyJson(request); const state = await loadState(env); const lic = requireCryptoRuntime(state, body);
  const token = String(body.telegram_token || '').trim(), chatId = String(body.telegram_chat_id || '').trim();
  if (!token && !chatId) {
    Object.assign(lic, { telegram_token:'', telegram_chat_id:'', telegram_bot_username:'' });
    await saveState(env, state); return json({ success:true, configured:false });
  }
  if (!token || !chatId) return json({ success:false, error:'Bot token ve Chat ID birlikte gerekli' }, 400);
  const me = await telegramApi(token, 'getMe', {});
  if (!me.ok) return json({ success:false, error:'Telegram bot token gecersiz' }, 400);
  const chat = await telegramApi(token, 'getChat', { chat_id:chatId });
  const chatRow = chat.data && chat.data.result || {};
  if (!chat.ok || !chatRow.id) return json({ success:false, error:'Ozel sohbet bulunamadi; bota once /start gonder' }, 400);
  if (String(chatRow.type || '').toLowerCase() !== 'private') return json({ success:false, error:'Sadece ozel Telegram sohbeti kabul edilir; grup ve kanal yasak' }, 400);
  if (String(chatRow.id) !== chatId) return json({ success:false, error:'Chat ID dogrulanamadi' }, 400);
  Object.assign(lic, { telegram_token:token, telegram_chat_id:chatId, telegram_bot_username:String(me.data && me.data.result && me.data.result.username || ''), telegram_connected_at:now() });
  await saveState(env, state);
  await telegramApi(token, 'sendMessage', { chat_id:chatId, text:'✅ Nexus CryptoCrops baglandi. CAPTCHA bildirimleri yalnizca bu ozel sohbete gelecek.' });
  return json({ success:true, configured:true, bot_username:lic.telegram_bot_username });
}

async function telegramCaptchaCreate(request, env) {
  const body = await bodyJson(request); const state = await loadState(env); const lic = requireCryptoRuntime(state, body);
  const token = String(lic.telegram_token || '').trim(), chatId = String(lic.telegram_chat_id || '').trim();
  if (!token || !chatId) return json({ success:false, error:'Telegram ayarlanmamis' }, 400);
  const siteKey = String(body.site_key || '').trim();
  if (!siteKey || siteKey.length > 180 || !/^[A-Za-z0-9_-]+$/.test(siteKey)) return json({ success:false, error:'hCaptcha site key gecersiz' }, 400);
  const captchaId = 'cc_' + randomToken().replace(/[^A-Za-z0-9]/g, '').slice(0, 26);
  const incoming = new URL(request.url);
  const solveUrl = `${incoming.origin}/cryptocrops/telegram/captcha/${captchaId}`;
  const session = { captcha_id:captchaId, license_id:String(lic.id || ''), client_id:String(body.client_id || '').trim().slice(0,160), site_key:siteKey, kind:String(body.kind || 'captcha').slice(0,40), page_url:String(body.page_url || '').slice(0,500), status:'waiting', captcha_token:'', created_at:now(), created_epoch:Date.now(), telegram_message_id:'' };
  await writeTelegramCaptcha(env, session);
  const sent = await telegramApi(token, 'sendMessage', { chat_id:chatId, text:'🚨 CryptoCrops CAPTCHA acildi. Asagidaki butondan dogrulamayi tamamla.', reply_markup:{ inline_keyboard:[[{ text:'🧩 CAPTCHA COZ', url:solveUrl }]] }, disable_web_page_preview:true });
  if (!sent.ok) { await writeValue(env, captchaSessionKey(captchaId), null); return json({ success:false, error:'Telegram mesaji gonderilemedi' }, 400); }
  session.telegram_message_id = String(sent.data && sent.data.result && sent.data.result.message_id || '');
  await writeTelegramCaptcha(env, session); return json({ success:true, captcha_id:captchaId, poll_ms:1800, solve_url:solveUrl });
}

async function telegramCaptchaStatus(request, env) {
  const url = new URL(request.url); const body = Object.fromEntries(url.searchParams.entries()); const state = await loadState(env); const lic = requireCryptoRuntime(state, body);
  const session = await readTelegramCaptcha(env, body.captcha_id);
  if (!session || String(session.license_id || '') !== String(lic.id || '')) return json({ success:false, error:'CAPTCHA oturumu bulunamadi' }, 404);
  const solved = session.status === 'solved' && !!session.captcha_token;
  return json({ success:true, status:solved ? 'solved' : String(session.status || 'waiting'), solved, captcha_token:solved ? session.captcha_token : '', site_key:String(session.site_key || ''), kind:String(session.kind || 'captcha') }, 200, { 'Cache-Control':'no-store' });
}

async function telegramCaptchaAck(request, env) {
  const body = await bodyJson(request); const state = await loadState(env); const lic = requireCryptoRuntime(state, body);
  const session = await readTelegramCaptcha(env, body.captcha_id);
  if (!session || String(session.license_id || '') !== String(lic.id || '')) return json({ success:false, error:'CAPTCHA oturumu bulunamadi' }, 404);
  session.status = 'consumed'; session.consumed_at = now(); session.captcha_token = '';
  if (session.telegram_message_id && lic.telegram_token && lic.telegram_chat_id) await telegramApi(lic.telegram_token, 'deleteMessage', { chat_id:lic.telegram_chat_id, message_id:session.telegram_message_id });
  await writeTelegramCaptcha(env, session); return json({ success:true });
}

async function telegramCaptchaRetry(request, env) {
  const body = await bodyJson(request); const state = await loadState(env); const lic = requireCryptoRuntime(state, body);
  const session = await readTelegramCaptcha(env, body.captcha_id);
  if (!session || String(session.license_id || '') !== String(lic.id || '')) return json({ success:false, error:'CAPTCHA oturumu bulunamadi' }, 404);
  if (session.status === 'consumed') return json({ success:true, status:'consumed' });
  session.status = 'waiting'; session.captcha_token = ''; session.retry_at = now();
  await writeTelegramCaptcha(env, session); return json({ success:true, status:'waiting' });
}

async function telegramCaptchaProgress(env, captchaId) {
  const session = await readTelegramCaptcha(env, captchaId);
  if (!session) return json({ success:false, status:'missing' }, 404, { 'Cache-Control':'no-store' });
  return json({ success:true, status:String(session.status || 'waiting') }, 200, { 'Cache-Control':'no-store' });
}

async function telegramCaptchaSolve(request, env) {
  const body = await bodyJson(request); const session = await readTelegramCaptcha(env, body.captcha_id);
  const captchaToken = String(body.captcha_token || '').trim();
  if (!session) return json({ success:false, error:'CAPTCHA oturumu bulunamadi' }, 404);
  if (captchaToken.length < 20) return json({ success:false, error:'CAPTCHA token gecersiz' }, 400);
  if (session.status === 'consumed') return json({ success:true, already_processed:true });
  if (!['waiting','solved'].includes(session.status)) return json({ success:false, error:'CAPTCHA oturumu kapandi' }, 410);
  Object.assign(session, { captcha_token:captchaToken, status:'solved', solved_at:now() });
  await writeTelegramCaptcha(env, session); return json({ success:true });
}

async function telegramCaptchaPage(env, captchaId) {
  const session = await readTelegramCaptcha(env, captchaId);
  if (!session) return new Response('<h3>CAPTCHA oturumu bulunamadi veya suresi doldu. Botun gonderdigi en yeni baglantiyi ac.</h3>', { status:404, headers:{ 'Content-Type':'text/html; charset=utf-8', 'Cache-Control':'no-store' } });
  if (session.status === 'consumed') return new Response('<h3>✅ CAPTCHA tamamlandi. Bot devam ediyor.</h3>', { status:200, headers:{ 'Content-Type':'text/html; charset=utf-8', 'Cache-Control':'no-store' } });
  const safeId = String(captchaId || '').replace(/[^A-Za-z0-9_-]/g, '');
  const clientId = String(session.client_id || '').replace(/[^A-Za-z0-9_-]/g, '');
  const target = `https://cryptocrops.net/earn/?nexus_telegram=${encodeURIComponent(safeId)}&nexus_client=${encodeURIComponent(clientId)}`;
  return new Response(null, { status:302, headers:{ Location:target, 'Cache-Control':'no-store', ...CORS } });
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
  state.cryptocrops.telegram_captchas ||= {};
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
  tamper_at:x.tamper_at || '', tamper_report:x.tamper_report || {}, telegram_configured:!!(x.telegram_token && x.telegram_chat_id), created_at:x.created_at || '', last_seen_at:x.last_seen_at || '', last_page:x.last_page || '' }; }
function summarize(b) { return { name:b.name || '', hash:b.hash || '', version:b.version || 0, updated_at:b.updated_at || '', uploaded:!!b.content }; }
function requireAdmin(request, env) { if (!env.ADMIN_TOKEN || request.headers.get('X-Admin-Token') !== env.ADMIN_TOKEN) throw new HttpError(401, 'Unauthorized'); }
function generateKey(app) { const prefix = app === 'zuncia' ? 'ZNC' : app === 'aztlacoin' ? 'AZT' : app === 'lightningminer' ? 'NXL' : 'MBF'; return `${prefix}-${randomHex(2)}-${randomHex(2)}-${randomHex(2)}-${randomHex(2)}`.toUpperCase(); }
function randomHex(bytes) { const a = crypto.getRandomValues(new Uint8Array(bytes)); return [...a].map(x => x.toString(16).padStart(2,'0')).join(''); }
function randomToken() { const a = crypto.getRandomValues(new Uint8Array(32)); return btoa(String.fromCharCode(...a)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,''); }
async function sha256(text) { const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)); return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2,'0')).join(''); }
function xorBase64(text, keyText) { const p = new TextEncoder().encode(text), k = new TextEncoder().encode(keyText || 'minerbytsfree'), out = new Uint8Array(p.length); for (let i=0;i<p.length;i++) out[i] = p[i] ^ k[i % k.length]; let s=''; for (let i=0;i<out.length;i+=0x8000) s += String.fromCharCode(...out.subarray(i,i+0x8000)); return btoa(s); }
async function bodyJson(request) { try { return await request.json(); } catch { return {}; } }
function now() { return new Date().toISOString(); }
function json(data, status=200, headers={}) { const actual = data && data.__status || status; return new Response(JSON.stringify(data), { status:actual, headers:{ 'Content-Type':'application/json; charset=utf-8', ...CORS, ...headers } }); }
function withCors(response) { const h = new Headers(response.headers); for (const [k,v] of Object.entries(CORS)) h.set(k,v); return new Response(response.body, { status:response.status, statusText:response.statusText, headers:h }); }
class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }
