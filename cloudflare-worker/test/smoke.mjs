import worker from '../src/index.js';

const rows = new Map();
rows.set('minerbytsfree_runtime', {
  project: 'minerbytsfree', licenses: [], settings: { heartbeat_seconds: 30 },
  zuncia: { licenses: [], settings: { heartbeat_seconds: 30 } },
  aztlacoin: { licenses: [], settings: { heartbeat_seconds: 30 } },
  cryptocrops: { licenses: [{ id:'1', name:'Test', key:'MBF-TEST', active:true, allowed_client_id:'client-1' }], settings: { heartbeat_seconds:30 } },
  lightningminer: { licenses: [], settings: { heartbeat_seconds:30 } }
});
rows.set('cryptocrops_bot_bundle', { name:'bot.txt', content:'console.log("ok")', hash:'hash-1', version:1 });

globalThis.fetch = async (input, init = {}) => {
  const request = input instanceof Request ? input : new Request(input, init);
  const url = new URL(request.url);
  if (url.hostname === 'primary.invalid') return new Response('suspended', { status:503 });
  if (url.hostname === 'api.telegram.org') {
    if (url.pathname.endsWith('/getChat')) return Response.json({ ok:true, result:{ id:777, type:'private', username:'test_user' } });
    if (url.pathname.endsWith('/getMe')) return Response.json({ ok:true, result:{ id:12345, username:'nexus_test_bot' } });
    return Response.json({ ok:true, result:{ message_id:99 } });
  }
  if (url.hostname !== 'db.invalid') throw new Error(`unexpected fetch ${url}`);
  if (request.method === 'GET') {
    const match = url.searchParams.get('key') || '';
    const key = decodeURIComponent(match.replace(/^eq\./, ''));
    return Response.json(rows.has(key) ? [{ value:rows.get(key) }] : []);
  }
  const payload = await request.json(); rows.set(payload.key, payload.value);
  return new Response(null, { status:201 });
};

const env = {
  PRIMARY_ORIGIN:'https://primary.invalid', PROJECT_NAME:'minerbytsfree',
  SUPABASE_URL:'https://db.invalid', SUPABASE_SERVICE_KEY:'secret', ADMIN_TOKEN:'admin'
};

const authRequest = new Request('https://gateway.invalid/cryptocrops/api/auth', {
  method:'POST', headers:{ 'Content-Type':'application/json' },
  body:JSON.stringify({ license_key:'MBF-TEST', client_id:'client-1', script_id:'script-1' })
});
const authResponse = await worker.fetch(authRequest, env);
const auth = await authResponse.json();
if (!auth.success || !auth.token) throw new Error(`auth failed: ${JSON.stringify(auth)}`);
if (rows.get('nexus_router_control')?.mode !== 'secondary') throw new Error('router did not persist secondary mode');

const heartbeatResponse = await worker.fetch(new Request('https://gateway.invalid/cryptocrops/api/heartbeat', {
  method:'POST', headers:{ 'Content-Type':'application/json' },
  body:JSON.stringify({ token:auth.token, client_id:'client-1', script_id:'script-1' })
}), env);
const heartbeat = await heartbeatResponse.json();
if (!heartbeat.success) throw new Error(`heartbeat failed: ${JSON.stringify(heartbeat)}`);

const runtime = { token:auth.token, license_key:'MBF-TEST', client_id:'client-1', script_id:'script-1' };
const registerResponse = await worker.fetch(new Request('https://gateway.invalid/cryptocrops/api/telegram/register', {
  method:'POST', headers:{ 'Content-Type':'application/json' },
  body:JSON.stringify({ ...runtime, telegram_token:'123456:TEST_TOKEN', telegram_chat_id:'777' })
}), env);
const registered = await registerResponse.json();
if (!registered.success) throw new Error(`telegram register failed: ${JSON.stringify(registered)}`);

const createResponse = await worker.fetch(new Request('https://gateway.invalid/cryptocrops/api/telegram/captcha/create', {
  method:'POST', headers:{ 'Content-Type':'application/json' },
  body:JSON.stringify({ ...runtime, kind:'farm', site_key:'10000000-ffff-ffff-ffff-000000000001', page_url:'https://cryptocrops.net/farm/' })
}), env);
const created = await createResponse.json();
if (!created.success || !created.captcha_id) throw new Error(`captcha create failed: ${JSON.stringify(created)}`);
const expectedSolveUrl = `https://gateway.invalid/cryptocrops/telegram/captcha/${created.captcha_id}`;
if (created.solve_url !== expectedSolveUrl) throw new Error(`wrong solve url: ${created.solve_url}`);

const pageResponse = await worker.fetch(new Request(created.solve_url), env);
const redirectUrl = pageResponse.headers.get('Location') || '';
if (pageResponse.status !== 302 || !redirectUrl.startsWith('https://cryptocrops.net/earn/?nexus_telegram=') || !redirectUrl.includes('nexus_client=client-1')) throw new Error(`same-origin captcha redirect failed: ${pageResponse.status} ${redirectUrl}`);

const captchaToken = 'test-captcha-token-that-is-long-enough';
const solveResponse = await worker.fetch(new Request('https://gateway.invalid/cryptocrops/api/telegram/captcha/solve', {
  method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ captcha_id:created.captcha_id, captcha_token:captchaToken })
}), env);
const solved = await solveResponse.json();
if (!solved.success) throw new Error(`captcha solve failed: ${JSON.stringify(solved)}`);

const statusUrl = new URL('https://gateway.invalid/cryptocrops/api/telegram/captcha/status');
Object.entries({ ...runtime, captcha_id:created.captcha_id }).forEach(([key,value]) => statusUrl.searchParams.set(key, value));
const statusResponse = await worker.fetch(new Request(statusUrl), env);
const status = await statusResponse.json();
if (!status.success || !status.solved || status.captcha_token !== captchaToken) throw new Error(`captcha token relay failed: ${JSON.stringify(status)}`);

const ackResponse = await worker.fetch(new Request('https://gateway.invalid/cryptocrops/api/telegram/captcha/ack', {
  method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ ...runtime, captcha_id:created.captcha_id })
}), env);
const ack = await ackResponse.json();
if (!ack.success) throw new Error(`captcha ack failed: ${JSON.stringify(ack)}`);
const progressResponse = await worker.fetch(new Request(`https://gateway.invalid/cryptocrops/api/telegram/captcha/progress/${created.captcha_id}`), env);
const progress = await progressResponse.json();
if (!progress.success || progress.status !== 'consumed') throw new Error(`captcha consume state failed: ${JSON.stringify(progress)}`);

console.log('cloudflare worker smoke test: ok');
