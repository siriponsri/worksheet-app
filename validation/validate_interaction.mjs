/* =========================================================================
   Interaction regressions a type-check cannot see
   -------------------------------------------------------------------------
   Needs a running server and a browser, so it is not in the default gate run:
       python3 server/pdf_server.py &
       node validation/validate_interaction.mjs

   Each case here is a bug that actually shipped into a build and was caught
   by driving the app, not by reading the diff.

   1. v7.1q keyed <main> on the full pathname so the route transition would
      replay. That remounted the whole workspace when the record key changed,
      which silently threw away every ticked row the moment somebody opened
      one of them to check it before printing.

   2. v7.1t added the per-machine quality choice. A setting that stores a
      value and changes nothing is the failure mode worth guarding: these
      assertions check that each option reaches BOTH the CSS (data-motion)
      and the 3D shelf (the canvas's actual render ratio), and that "full"
      genuinely stops the governor demoting — verified here under software
      rendering, which would otherwise demote within seconds.
   ========================================================================= */
import { chromium } from 'playwright';
const browserPath = process.env.ANF3_BROWSER_PATH || chromium.executablePath();
const baseUrl = process.env.ANF3_BROWSER_BASE || 'http://127.0.0.1:5173';
const b = await chromium.launch({ executablePath: browserPath });
const ctx = await b.newContext({ viewport:{width:1440,height:900} });
await ctx.addInitScript(()=>{ try{ localStorage.setItem('anf3.operator.v2', JSON.stringify({name:'สมชาย ใจดี',code:'4417'})); Object.defineProperty(navigator, 'onLine', { configurable: true, get: () => sessionStorage.getItem('anf3-validation-offline') !== '1' }); }catch{} });
const p = await ctx.newPage();
await p.goto(`${baseUrl}/#/records/water/pw-prw?building=Building%2010`, { waitUntil:'domcontentloaded' });
await p.evaluate(async () => {
  const open=()=>new Promise((res,rej)=>{const r=indexedDB.open('anf3-read-cache-v1',1);
    r.onupgradeneeded=()=>{const d=r.result;for(const s of ['records','searchPages','metadata'])if(!d.objectStoreNames.contains(s))d.createObjectStore(s,{keyPath:'id'});};
    r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error);});
  const db=await open(); const put=(s,v)=>new Promise((res,rej)=>{const tx=db.transaction(s,'readwrite');const rq=tx.objectStore(s).put(v);rq.onsuccess=()=>res();rq.onerror=()=>rej(rq.error);});
  for (const no of ['WT-25-0001','WT-25-0002','WT-25-0003'])
    await put('records',{id:`water:pw-prw:${no}`,domain:'water',workflow:'pw-prw',recordKey:no,
      record:{worksheetNo:no,building:'Building 10',samplingDate:'2026-09-01'},samples:[],fetchedAt:new Date().toISOString()});
  await put('searchPages',{id:'pw-prw|building=building 10',fetchedAt:new Date().toISOString(),
    items:['WT-25-0001','WT-25-0002','WT-25-0003'].map(no=>({recordKey:no,worksheetNo:no,recordId:no,title:no,building:'Building 10'}))});
});
await p.evaluate(() => { sessionStorage.setItem('anf3-validation-offline', '1'); window.dispatchEvent(new Event('offline')); });
await p.reload({ waitUntil:'domcontentloaded' }); await p.waitForTimeout(1500);
const cachedDialog = p.getByRole('alertdialog', { name: 'No internet connection' });
if (await cachedDialog.isVisible()) await cachedDialog.getByRole('button', { name: 'Read cached' }).click();
await p.getByRole('row').filter({ hasText: 'WT-25-0001' }).waitFor({ state: 'visible', timeout: 10000 });

// tick two rows, then open a record — the ticks must survive
const rows = p.locator('.record-table tbody tr');
await rows.nth(0).getByRole('switch').click();
await rows.nth(1).getByRole('switch').click();
const before = await p.locator('.record-table [role="switch"][aria-checked="true"]').count();
console.log('ticked before opening a record:', before);
await rows.nth(0).getByRole('button', { name: 'Details' }).click();
await p.waitForTimeout(1600);
const after = await p.locator('.record-table [role="switch"][aria-checked="true"]').count();
console.log('ticked after  opening a record:', after);
const fail = [];
if (after !== before) fail.push('selection lost on navigation');
else console.log('OK — selection survived');

await p.evaluate(() => { sessionStorage.removeItem('anf3-validation-offline'); window.dispatchEvent(new Event('online')); });
await p.waitForTimeout(300);

await p.goto(`${baseUrl}/#/settings`, { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(1200);

const options = await p.locator('.quality-option').count();
console.log('quality options offered:', options);
if (options !== 3) fail.push(`expected 3 options, saw ${options}`);

const chosen = async () => p.locator('.quality-option.is-chosen strong').innerText();
console.log('default choice:', await chosen());
if ((await chosen()) !== 'อัตโนมัติ') fail.push('default is not auto');

const motionAttr = async () => p.evaluate(() => document.documentElement.dataset.motion);
console.log('data-motion at default:', await motionAttr());

// pick FAST -> data-motion must flip and survive a reload
await p.locator('.quality-option:has(input[value="fast"])').click();
await p.waitForTimeout(400);
console.log('after choosing เร็ว  -> data-motion:', await motionAttr(), '| chosen:', await chosen());
if ((await motionAttr()) !== 'reduced') fail.push('choosing fast did not set data-motion=reduced');

await p.reload({ waitUntil: 'domcontentloaded' }); await p.waitForTimeout(1000);
console.log('after reload        -> data-motion:', await motionAttr(), '| chosen:', await chosen());
if ((await motionAttr()) !== 'reduced') fail.push('the choice did not survive a reload');

// FAST must actually reach the 3D shelf: dpr 1, no supersampling
await p.goto(`${baseUrl}/#/`, { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(5000);
const fastCanvas = await p.evaluate(() => {
  const c = document.querySelector('canvas');
  return c ? +(c.width / c.clientWidth).toFixed(2) : null;
});
console.log('shelf render ratio on เร็ว :', fastCanvas);
if (fastCanvas !== null && fastCanvas > 1.05) fail.push(`fast should render at 1x, got ${fastCanvas}`);

// FULL must restore supersampling
await p.goto(`${baseUrl}/#/settings`, { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(800);
await p.locator('.quality-option:has(input[value="full"])').click();
await p.waitForTimeout(400);
console.log('after choosing เต็มที่ -> data-motion:', await motionAttr());
if ((await motionAttr()) !== 'full') fail.push('full did not set data-motion=full');

await p.goto(`${baseUrl}/#/`, { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(5000);
const fullCanvas = await p.evaluate(() => {
  const c = document.querySelector('canvas');
  return c ? +(c.width / c.clientWidth).toFixed(2) : null;
});
console.log('shelf render ratio on เต็มที่:', fullCanvas);
if (fullCanvas !== 1.5) fail.push(`full should render at 1.5x, got ${fullCanvas}`);

// and FULL must not let the governor demote it, even under software rendering
const demoted = await p.evaluate(() => document.documentElement.dataset.shelfQuality || 'none');
console.log('governor demotion while on เต็มที่:', demoted, '(software rendering here would demote if it could)');
if (demoted !== 'none') fail.push(`full was demoted to ${demoted} despite the operator pinning it`);


console.log(fail.length ? '\nFAILURES:\n  ' + fail.join('\n  ') : '\nall interaction checks passed');
await b.close();
process.exit(fail.length ? 1 : 0);
