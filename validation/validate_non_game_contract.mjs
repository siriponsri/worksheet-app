import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const failures = [];
const warnings = [];
const controlledFlag = process.argv.indexOf('--controlled-dir');
const controlledValue = controlledFlag >= 0 ? process.argv[controlledFlag + 1] : process.env.ANF3_CONTROLLED_ROOT;
const CONTROLLED_ROOT = controlledValue ? path.resolve(ROOT, controlledValue) : null;

if (controlledFlag >= 0 && !controlledValue) {
  failures.push('--controlled-dir requires a directory');
}
if (CONTROLLED_ROOT && !fs.existsSync(CONTROLLED_ROOT)) {
  failures.push(`controlled release directory is missing: ${CONTROLLED_ROOT}`);
}

function read(relativePath) {
  const absolutePath = path.join(ROOT, relativePath);
  if (!fs.existsSync(absolutePath)) {
    failures.push(`${relativePath}: missing`);
    return '';
  }
  return fs.readFileSync(absolutePath, 'utf8');
}

function readOptional(relativePath, { controlled = false } = {}) {
  const absolutePath = controlled && CONTROLLED_ROOT
    ? path.join(CONTROLLED_ROOT, relativePath)
    : path.join(ROOT, relativePath);
  if (!fs.existsSync(absolutePath)) {
    if (controlled && CONTROLLED_ROOT) failures.push(`${relativePath}: missing from controlled release`);
    return '';
  }
  return fs.readFileSync(absolutePath, 'utf8');
}

function pass(message) {
  console.log(`PASS ${message}`);
}

function fail(message) {
  failures.push(message);
  console.log(`FAIL ${message}`);
}

function warn(message) {
  warnings.push(message);
  console.log(`WARN ${message}`);
}

function assert(condition, message) {
  if (condition) pass(message);
  else fail(message);
}

const expectedScripts = [
  'google/app-scripts/air-test.gs',
  'google/app-scripts/RPP2-air-record.gs',
  'google/app-scripts/water-r.gs',
  'google/app-scripts/RPP2-water-record.gs',
  'google/app-scripts/Testing.gs',
  'google/app-scripts/RPP2-cv-record.gs'
];

console.log('ANF3 non-game contract audit');
console.log(`root=${ROOT}`);
console.log(`mode=${CONTROLLED_ROOT ? `controlled (${CONTROLLED_ROOT})` : 'public source'}`);

const typedAppData = read('apps/web/src/appData.ts');
const typedBinderDefinitions = typedAppData.split(/\r?\n/)
  .filter((line) => /^\s*\{ id: '[^']+'.*state: '[^']+'/.test(line))
  .map((line) => {
    const match = line.match(/^\s*\{ id: '([^']+)'\s*,\s*groupId: '([^']+)'\s*,\s*buildingFilter: '([^']+)'\s*,\s*workflowId: '([^']+)'\s*,\s*label: '([^']+)'[^\n]*state: '([^']+)'/);
    return match && { id: match[1], group: match[2], building: match[3], workflow: match[4], label: match[5], state: match[6] };
  })
  .filter(Boolean);
const expectedBinders = typedBinderDefinitions.filter(({ state }) => state === 'active').map(({ id }) => id);
const expectedFrontendBinders = typedBinderDefinitions.map(({ id }) => id);
const typedBinders = new Map(typedBinderDefinitions.map(({ id, group, building, workflow, label }) => [id, { group, building, workflow, label }]));
assert(expectedBinders.length > 0, 'Typed frontend registry declares active binders');

const matrix = readOptional('docs/CABINET_WORKFLOW_MATRIX.md', { controlled: true });
/* The active table stops at the first "### Inside …" sub-table: those rows
   describe what is inside a binder, not binders on the shelf. */
const activeMatrixSection = (matrix.split('## Reserve instances')[0].split('## Active binder instances')[1] || '').split('### Legacy source-location examples')[0];
const matrixIds = [...activeMatrixSection.matchAll(/^\| `([^`]+)` \|/gm)].map((match) => match[1]);
if (matrix) {
  assert(matrixIds.length === expectedBinders.length, `Cabinet matrix matches typed active binder count (${expectedBinders.length}, found ${matrixIds.length})`);
  assert(expectedBinders.every((id) => matrixIds.includes(id)), 'Cabinet matrix contains every required active destination');
  assert(new Set(matrixIds).size === matrixIds.length, 'Cabinet matrix has no duplicate active row');
} else if (!CONTROLLED_ROOT) {
  warn('Controlled cabinet matrix is not in the public checkout; using the typed frontend registry as the source contract');
}

/* IDs alone can pass while columns are shifted. Compare the matrix's
   building/work/label semantics with the typed registry as well. */
const normalizeSemantic = (value) => String(value || '')
  .replace(/[\u2013\u2014]/g, '-')
  .replace(/[^a-z0-9]+/gi, '')
  .toLowerCase();
const matrixRows = activeMatrixSection.split(/\r?\n/)
  .filter((line) => /^\| `[^`]+` \|/.test(line))
  .map((line) => line.split('|').slice(1, -1).map((cell) => cell.trim().replace(/^`|`$/g, '')));
const secondaryMatches = (workflow, id, value) => {
  const text = normalizeSemantic(value);
  if (workflow === 'em-air') return text.includes('passiveactive') || text.includes('passiveandactive') || text.includes('environmentalmonitoringair');
  if (workflow === 'cv') return text.includes('cvselector') || text.includes('cleaningvalidationroutes');
  if (workflow === 'pw-prw') return text.includes('allsupportedwatertypes') || text.includes('pwprwandwfipuslogicalroutes');
  if (workflow === 'wfi-pus') return text.includes('wfipusrecords');
  if (workflow === 'compressed-air') {
    return id === 'b16-ca-n2'
      ? text.includes('can2selectororall')
      : text.includes('gastypeca') || text.includes('compressedairnitrogenroute');
  }
  return false;
};
if (matrix && matrixRows.length) {
  for (const row of matrixRows) {
    const [id, group, building, workflow, label, secondary] = row;
    const typed = typedBinders.get(id);
    assert(Boolean(typed), `Cabinet matrix row ${id} has a typed registry entry`);
    if (!typed) continue;
    assert(normalizeSemantic(group) === normalizeSemantic(typed.group), `${id} matrix group matches typed registry`);
    assert(normalizeSemantic(building) === normalizeSemantic(typed.building), `${id} matrix building filter matches typed registry`);
    assert(normalizeSemantic(workflow) === normalizeSemantic(typed.workflow), `${id} matrix workflow matches typed registry`);
    assert(normalizeSemantic(label) === normalizeSemantic(typed.label), `${id} matrix display label matches typed registry`);
    assert(secondaryMatches(typed.workflow, id, secondary), `${id} matrix secondary filter matches workflow scope`);
  }
}

const scriptContents = [];
for (const relativePath of expectedScripts) {
  const source = read(relativePath);
  if (source) scriptContents.push([relativePath, source]);
}
assert(scriptContents.length === expectedScripts.length, 'Exactly six required copy-ready Apps Script files exist');
const scriptFiles = [];
function collectCodeGs(directory) {
  if (!fs.existsSync(directory)) return;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) collectCodeGs(absolutePath);
    else if (entry.isFile() && entry.name.endsWith('.gs')) scriptFiles.push(path.relative(ROOT, absolutePath).replaceAll(path.sep, '/'));
  }
}
collectCodeGs(path.join(ROOT, 'google/app-scripts'));
assert(scriptFiles.length === 6, `google/app-scripts contains exactly six deployable .gs files (found ${scriptFiles.length})`);

const requiredConstantPatterns = [
  /ANF3_API_VERSION/,
  /ANF3_IMPLEMENTATION_VERSION/,
  /ANF3_TIME_ZONE\s*=\s*['"]Asia\/Bangkok['"]/,
  /ANF3_DOMAIN/
];
const systemScriptPaths = new Set([
  'google/app-scripts/RPP2-air-record.gs',
  'google/app-scripts/RPP2-water-record.gs',
  'google/app-scripts/RPP2-cv-record.gs'
]);
for (const [relativePath, source] of scriptContents.filter(([path]) => systemScriptPaths.has(path))) {
  const patterns = relativePath.endsWith('RPP2-cv-record.gs') ? [] : requiredConstantPatterns;
  const missing = patterns.filter((pattern) => !pattern.test(source));
  assert(missing.length === 0, `${relativePath} declares shared API/version/time-zone/domain constants`);
  assert(/verify[A-Za-z]+Setup\s*\(/.test(source), `${relativePath} exposes a verify…Setup function`);
  if (!relativePath.endsWith('RPP2-cv-record.gs')) assert(/PropertiesService/.test(source), `${relativePath} uses Script Properties for configuration`);
  assert(!/(?:syncToken|ANF3_SYNC_TOKEN|Bearer)\s*[:=]\s*['"][^'"$]{8,}/i.test(source), `${relativePath} has no obvious hardcoded token`);
}

const appData = read('apps/web/src/appData.ts');
const appSource = read('apps/web/src/App.tsx');
assert(/b10-pw-prw|binderInstances|CABINET_WORKFLOW_MATRIX/.test(appData), 'Frontend derives from a typed Cabinet/binder registry');
assert(/Cabinet|List/.test(appSource), 'Frontend exposes Cabinet/List parity controls');
assert(expectedFrontendBinders.every((id) => appData.includes(id)), 'Frontend contains every binder ID on the shelf');

const cvRouting = readOptional('docs/CV_TEMPLATE_ROUTING_CONTRACT.md', { controlled: true });
const pdfServer = read('server/pdf_server.py');
for (const route of ['cleaning-validation-contact', 'cleaning-validation-rinse-pour', 'cleaning-validation-rinse-membrane']) {
  if (cvRouting) assert(cvRouting.includes(route), `CV routing contract includes ${route}`);
  assert(pdfServer.includes(route), `PDF service includes ${route}`);
}
if (!cvRouting && !CONTROLLED_ROOT) warn('Controlled CV template routing contract is not in the public checkout; server and frontend route registries are checked instead');
assert(/TEMPLATE_DIR/.test(pdfServer) && /send_file\(pdf_path/.test(pdfServer), 'PDF service uses server-owned template/output resolution');
assert(/ANF3_HOST['"]?\s*,\s*['"]127\.0\.0\.1['"]/.test(pdfServer), 'PDF service defaults to loopback binding');

if (!pdfServer.includes('cleaning-validation-rinse-pour') || !pdfServer.includes('cleaning-validation-rinse-membrane')) {
  warn('CV Rinse dedicated template routes are not yet implemented; keep Rinse PDF blocked');
}
if (!/b10-pw-prw|binderInstances/.test(appData)) {
  warn('Frontend Cabinet registry is not yet implemented; current domain folders are not matrix parity');
}

console.log(`\nSummary: ${failures.length ? 'INCOMPLETE' : 'PASS'}; failures=${failures.length}; warnings=${warnings.length}`);
if (failures.length) process.exitCode = 1;
