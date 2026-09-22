const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const bot = fs.readFileSync(path.join(root, '.codex/botazalt.txt'), 'utf8');
new vm.Script(bot);
const selection = bot.slice(bot.indexOf('  function missionTarget('), bot.indexOf('  async function recordGameResult('));
function scheduler(options = {}) {
  let seed = 12345;
  const math = Object.create(Math);
  math.random = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
  const c = vm.createContext({Math: math, Date});
  vm.runInContext(`
    const GAMES = ['puzzle','clicker','memory','math','catch','blockbreaker','ufo','match3'].map(id=>({id}));
    const prefs={smart:true}, cooldowns={}, retryAfter={}, selectionHistory=new Map();
    let selectionNumber=0,lastSelectedGame='',missionsFresh=true;
    let missionRows=['memory','math'].map(id=>({available:true,progress:0,mission:{requirement_type:'win_game',requirement_target:id,requirement_value:10}}));
    ${selection}
    globalThis.pick=selectGame;
    globalThis.configure=fn=>fn({prefs,cooldowns,retryAfter,missionRows,GAMES});
  `, c);
  return c;
}
const c = scheduler();
let missionCount = 0, previous = '', counts = {};
for (let i=0; i<10000; i++) {
  const g = c.pick().id;
  assert.notEqual(g, previous, 'must not repeat with alternatives');
  previous=g; counts[g]=(counts[g]||0)+1;
  if (['memory','math'].includes(g)) missionCount++;
}
assert(missionCount > 5800 && missionCount < 6200, JSON.stringify({missionCount}));
assert.equal(Object.keys(counts).length,8);
assert(Math.min(...Object.values(counts))>500);
c.configure(({missionRows})=>missionRows.forEach(r=>r.estimated=10));
counts={}; for(let i=0;i<800;i++){const id=c.pick().id;counts[id]=(counts[id]||0)+1;}
assert(Math.max(...Object.values(counts))-Math.min(...Object.values(counts))<=2);
c.configure(({cooldowns,GAMES})=>GAMES.forEach(g=>cooldowns[g.id]=Date.now()+60000));
assert.equal(c.pick(),null);
c.configure(({cooldowns})=>cooldowns.catch=0);
assert.equal(c.pick().id,'catch'); assert.equal(c.pick().id,'catch');
c.configure(({retryAfter})=>retryAfter.catch=Date.now()+60000);
assert.equal(c.pick(),null);
const expired=scheduler();
expired.configure(({missionRows})=>missionRows.forEach(r=>r.reset_at='2000-01-01T00:00:00Z'));
counts={}; for(let i=0;i<800;i++){const id=expired.pick().id;counts[id]=(counts[id]||0)+1;}
assert.equal(Object.keys(counts).length,8);
assert(Math.max(...Object.values(counts))-Math.min(...Object.values(counts))<=2);

const panel = fs.readFileSync(path.join(root,'panel/e.py'),'utf8');
const template = panel.split("CLIENT_TEMPLATE = r'''")[1].split("'''")[0];
new vm.Script(template);
const security = template.slice(template.indexOf('    function buildSecurityPayload('),template.indexOf('    window.__MINERBYTSFREE_REPORT_F12__'));
async function securityTest(key, trusted=true, repeat=false) {
  const requests=[], listeners={}; let timers=0;
  const ctx = vm.createContext({
    window:{outerWidth:2000,innerWidth:300,outerHeight:1600,innerHeight:100,addEventListener:(event,fn)=>listeners[event]=fn},
    navigator:{userAgent:'test'},location:{href:'https://zuncia.com/game/index.php'},
    URLSearchParams,Image:class {},Blob,loadAuth:()=>({}),getSavedLicenseKey:()=>'',collectAccountId:()=>'',
    apiUrl:p=>p,gmRequest:async (...args)=>{requests.push(args);return {success:true}},showGate:()=>{},
    setTimeout:()=>timers++,setInterval:()=>timers++,clearInterval:()=>{},
  });
  vm.runInContext(`let sessionToken='',heartbeatTimer=null; const CLIENT_ID='test',SCRIPT_ID='test';${security};installSecurityShortcuts();`,ctx);
  assert.equal(timers,0,'geometry must not schedule lock checks');
  listeners.keydown({key,isTrusted:trusted,repeat,preventDefault(){},stopPropagation(){},stopImmediatePropagation(){}});
  await new Promise(resolve=>setImmediate(resolve));
  return requests;
}
(async()=>{
  assert.equal((await securityTest('Escape')).length,0);
  assert.equal((await securityTest('F12',false)).length,0);
  assert.equal((await securityTest('F12',true,true)).length,0);
  const requests=await securityTest('F12');
  assert.equal(requests.length,1);
  assert.equal(requests[0][2].source,'loader_keydown_v2');
  console.log(`PASS: 10,000 selections, ${missionCount/100}% mission share, all 8 games; no consecutive repeats, completed/expired tasks, cooldown/backoff; Zuncia geometry/synthetic keys ignored, real F12 retained.`);
})().catch(error=>{console.error(error);process.exitCode=1});
