import assert from 'node:assert/strict';
import fs from 'node:fs';

const read = (relativePath) => fs.readFileSync(new URL(`../${relativePath}`, import.meta.url), 'utf8');
const policy = read('apps/web/src/recordPolicy.ts');
const payload = read('apps/web/src/documentPayload.ts');
const server = read('server/pdf_server.py');
const system = read('google/app-scripts/RPP2-cv-record.gs');

for (const route of [
  'cleaning-validation-contact',
  'cleaning-validation-rinse-pour',
  'cleaning-validation-rinse-membrane'
]) {
  assert.match(policy, new RegExp(route), `${route} is present in frontend routing`);
  assert.match(server, new RegExp(route), `${route} is present in Flask routing`);
}

assert.match(policy, /testMethod/);
assert.match(payload, /resultAvg/);
assert.match(payload, /result\$\{suffix\}/);
assert.match(payload, /lotMembrane/);
assert.match(payload, /leftEm/);
assert.match(payload, /rightEm/);
assert.match(system, /records_cv_contact_B10/);
assert.match(system, /record_cv_rinse_B10/);
assert.doesNotMatch(system, /records_cv_samples/);

console.log('CV route and sample contract checks passed');
