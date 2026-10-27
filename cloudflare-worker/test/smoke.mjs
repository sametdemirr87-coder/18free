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

console.log('cloudflare worker smoke test: ok');
