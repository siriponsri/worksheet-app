import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} exists`);
  const open = source.indexOf('{', start);
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}' && --depth === 0) return source.slice(start, index + 1);
  }
  throw new Error(`${name} has an unterminated body`);
}

function loadBuildingMatcher(source, prefix) {
  const names = [`${prefix}FilterValues_`, `${prefix}Token_`, `${prefix}BuildingMatches_`];
  const context = {};
  const code = names.map((name) => extractFunction(source, name)).join('\n')
    + `\nthis.matcher = ${prefix}BuildingMatches_;`;
  vm.runInNewContext(code, context);
  return context.matcher;
}

const projects = {
  air: {
    user: read('google/app-scripts/air-test.gs'),
    system: read('google/app-scripts/RPP2-air-record.gs'),
    workflows: ['compressed-air', 'em-air']
  },
  water: {
    user: read('google/app-scripts/water-r.gs'),
    system: read('google/app-scripts/RPP2-water-record.gs'),
    workflows: ['pw-prw', 'wfi-pus']
  },
  cv: {
    user: read('google/app-scripts/Testing.gs'),
    system: read('google/app-scripts/RPP2-cv-record.gs'),
    workflows: ['cv']
  }
};

for (const [domain, project] of Object.entries(projects)) {
  assert.doesNotMatch(project.user, /ANF3_SYNC_TOKEN|X-ANF3-Sync-Token/, `${domain} user has no sync-token dependency`);
  assert.doesNotMatch(project.system, /ANF3_SYNC_TOKEN|X-ANF3-Sync-Token/, `${domain} system has no sync-token dependency`);
  assert.match(project.system, /LockService\.getScriptLock\(\)/, `${domain} serializes mutations`);
  assert.match(project.system, /action === 'search'|case 'search'/, `${domain} exposes search`);
  assert.match(project.system, /action === 'get'|case 'get'/, `${domain} exposes get`);
  assert.doesNotMatch(project.system, /error\.stack|stack:\s*error/, `${domain} does not expose stack traces`);
  for (const workflow of project.workflows) {
    assert.ok(project.system.includes(`'${workflow}'`), `${domain} allowlists ${workflow}`);
  }
}

assert.match(projects.air.system, /RECORDS_EM_ACTIVE.*records_em_B10.*records_em_OT/s, 'Air active shard allowlist');
assert.match(projects.water.system, /RECORDS_ROUTINE_ACTIVE.*records_pw_prw_B10.*records_pw_prw_OT/s, 'Water active shard allowlist');
assert.match(projects.water.system, /RECORDS_WFI_ACTIVE:\s*\['records_wfi_B16', 'records_wfi_OT'\]/, 'Water WFI uses workbook shards');
assert.match(projects.cv.system, /CONTACT_SHEETS:\s*\[/, 'CV contact shards match workbook');
assert.match(projects.cv.system, /records_cv_contact_B10.*records_cv_contact_OT/s, 'CV contact shard names match workbook');
assert.match(projects.cv.system, /RINSE_SHEETS:\s*\[/, 'CV rinse shards match workbook');
assert.match(projects.cv.system, /record_cv_rinse_B10.*record_cv_rinse_OT/s, 'CV rinse shard names match workbook');
assert.doesNotMatch(projects.cv.system, /records_cv_samples/, 'CV stores samplesJson in its parent workbook tabs');
assert.match(projects.cv.system, /prefix[\s\S]{0,120}CVR|CVR-YY/, 'CV rinse uses CVR prefix');
assert.match(projects.air.system, /Legacy backup records are read-only/, 'Air protects legacy backup');
assert.match(projects.water.system, /Legacy backup records are read-only/, 'Water protects legacy backup');

for (const [domain, prefix] of [['air', 'air'], ['water', 'water']]) {
  const matches = loadBuildingMatcher(projects[domain].system, prefix);
  assert.equal(matches('Building 10', 'Other'), false, `${domain} Other excludes Building 10`);
  assert.equal(matches('Building 12', 'Other'), false, `${domain} Other excludes Building 12`);
  assert.equal(matches('Building 16', 'Other'), false, `${domain} Other excludes Building 16`);
  assert.equal(matches('Building 11', 'Other'), true, `${domain} Other keeps Building 11`);
  assert.equal(matches('Building 19', 'Other'), true, `${domain} Other keeps Building 19`);
  assert.equal(matches('OSD-PW (Building 10)', 'Other'), true, `${domain} preserves unknown source text in Other`);
}

console.log('Apps Script security/read contracts: PASS');
