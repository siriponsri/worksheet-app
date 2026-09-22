import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const files = [
  ['js/print-em-air.js', 'em-air'],
  ['js/print-compressed-air.js', 'compressed-air'],
  ['em-air/list.html', 'em-air'],
  ['compressed-air/list.html', 'compressed-air']
];

for (const [file, workflow] of files) {
  const source = fs.readFileSync(file, 'utf8');
  if (file.endsWith('.js')) {
    assert.match(source, /fetchAllAirWorksheets/, `${file} must use the paginated logical Air search`);
    assert.ok(source.includes(`fetchAllAirWorksheets(scriptUrl, '${workflow}')`), `${file} must request its logical workflow`);
  }
  assert.doesNotMatch(source, /records_(?:em|ca)_(?:B10|B12|B16|OT)/, `${file} must not name physical shards`);
}
for (const file of ['js/print-em-air.js', 'js/print-compressed-air.js']) {
  const source = fs.readFileSync(file, 'utf8');
  assert.doesNotMatch(source, /result.data.filter/, `${file} must filter the defined logical response`);
  assert.match(source, /action=get&workflow=/, `${file} must retrieve the selected logical record detail`);
  assert.match(source, /seenCursors.has/, `${file} must reject a repeated cursor`);
  assert.match(source, /selectedData = null/, `${file} must fail closed before detail loading`);
  assert.match(source, /Select it again to retry/, `${file} must provide a retry path after detail failure`);
  assert.doesNotMatch(source, /:s*summary;/, `${file} must not fall back to a search summary for printing`);
}
for (const file of ['js/print-pw-prw.js', 'js/print-wfi-pus.js', 'js/print-em-air.js', 'js/print-compressed-air.js']) {
  const source = fs.readFileSync(file, 'utf8');
  assert.match(source, /formatResultValue/, `${file} must normalize count fields`);
}
for (const file of ['js/print-em-air.js', 'js/print-compressed-air.js']) {
  assert.match(fs.readFileSync(file, 'utf8'), /formatMeasurementValue/, `${file} must normalize measured fields`);
}

async function loadPaginationHelper(file, responses) {
  const context = {
    URLSearchParams,
    fetch: async (url) => {
      const cursor = new URL(String(url)).searchParams.get('cursor') || '';
      const response = responses.shift();
      assert.equal(cursor, response.cursor, `${file} must request the supplied nextCursor`);
      return { ok: true, status: 200, json: async () => response.payload };
    },
    document: { addEventListener() {} }, window: { location: { search: '' } },
    Storage: { get() { return ''; } }, console, setTimeout, UI: {},
  };
  vm.createContext(context);
  vm.runInContext(`${fs.readFileSync(file, 'utf8')}\nglobalThis.fetchPages = fetchAllAirWorksheets;`, context);
  return context;
}

for (const [file, workflow] of files.filter(([file]) => file.endsWith('.js'))) {
  const first = Array.from({ length: 100 }, (_, index) => ({ recordKey: `${workflow}-${index}` }));
  const second = [{ recordKey: `${workflow}-100` }];
  const context = await loadPaginationHelper(file, [
    { cursor: '', payload: { success: true, data: { items: first, nextCursor: 'page-2' } } },
    { cursor: 'page-2', payload: { success: true, data: { items: second, nextCursor: '' } } }
  ]);
  assert.equal((await context.fetchPages('https://example.test/exec', workflow)).length, 101, `${file} must aggregate all 101 summaries`);

  const repeated = await loadPaginationHelper(file, [
    { cursor: '', payload: { success: true, data: { items: [], nextCursor: 'again' } } },
    { cursor: 'again', payload: { success: true, data: { items: [], nextCursor: 'again' } } }
  ]);
  await assert.rejects(() => repeated.fetchPages('https://example.test/exec', workflow), /repeated cursor/);
}

const airSync = fs.readFileSync('google/app-scripts/air-test.gs', 'utf8');
assert.match(airSync, /samplingMode:\s*normalizeSamplingMode_\(row\[c\.method\]\)/,
  'Air sync must carry the source Method into each EM sample samplingMode');
assert.match(airSync, /token === 'settleplate' \|\| token === 'passive'.*return 'passive'/s,
  'Settle Plate/passive source methods must normalize to passive');
assert.match(airSync, /token === 'activeair' \|\| token === 'active'.*return 'active'/s,
  'Active Air/active source methods must normalize to active');
assert.match(airSync, /return '';/,
  'Unknown Air methods must remain blank rather than being fabricated');
console.log('Legacy Air logical-routing and numeric contracts passed');
