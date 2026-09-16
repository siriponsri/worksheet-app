/* One local evidence entry point. It never deploys, writes Sheets, or calls a
 * live endpoint; external checks remain informational. */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const reportPath = path.join(root, 'output', 'validation-report.json');
fs.mkdirSync(path.dirname(reportPath), { recursive: true });
const results = [];
const pnpm = 'pnpm';
const python = process.env.ANF3_PYTHON || 'python';

function run(name, command, args, evidenceClass = 'VERIFIED_BY_EXECUTION') {
  let actualCommand = command;
  let actualArgs = args;
  if (process.platform === 'win32' && command === 'pnpm') {
    actualCommand = process.env.ComSpec || 'cmd.exe';
    actualArgs = ['/d', '/s', '/c', ['pnpm', ...args].join(' ')];
  }
  const result = spawnSync(actualCommand, actualArgs, {
    cwd: root, encoding: 'utf8', timeout: 180000, windowsHide: true
  });
  const pass = result.status === 0;
  results.push({ name, command: [command, ...args].join(' '), result: pass ? 'PASS' : 'FAIL', evidenceClass,
    exitCode: result.status, stdout: result.stdout?.slice(-4000) || '', stderr: result.stderr?.slice(-4000) || '' });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${name} [${evidenceClass}]`);
  return pass;
}

const checks = [
  ['frontend unit tests', pnpm, ['test']],
  ['frontend type check', pnpm, ['check']],
  ['frontend production build', pnpm, ['build']],
  ['server tests', python, ['-m', 'pytest', 'server/tests', '-q']],
  ['launcher contract', 'node', ['validation/validate_launchers.mjs']],
  ['legacy CV/EM/CA mapping contract', 'node', ['validation/test_legacy_document_mapping.mjs']],
  ['legacy Air pagination contract', 'node', ['validation/test_legacy_air_contract.mjs']],
  ['deployment fixture and negative cases', 'node', ['validation/test_deployment_smoke.mjs']],
  ['Apps Script security contract', 'node', ['validation/test_apps_script_security.mjs']],
  ['CV package contract', python, ['validation/validate_cv_package.py']],
  ['CV route contract', 'node', ['validation/test_cv_contract.mjs']],
  ['worksheet numbering contract', 'node', ['validation/test_worksheet_numbering.mjs']],
  ['Games freeze contract', 'node', ['validation/test_games.mjs']],
  ['interaction contract', 'node', ['validation/validate_interaction.mjs']],
  ['style contract', 'node', ['validation/validate_styles.mjs']],
  ['frontend/server wiring contract', 'node', ['validation/validate_wiring.mjs', '--built']],
  ['non-game release contract', 'node', ['validation/validate_non_game_contract.mjs']],
  ['release structure contract', python, ['validation/validate_release.py']],
  ['document artifact validator source', python, ['-m', 'py_compile', 'validation/validate_document_artifacts.py']],
  ['working tree whitespace', 'git', ['diff', '--check', 'HEAD']],
];
function inspectRepositoryContracts() {
  const expectations = [
    [path.join(root, 'google', 'app-scripts', 'RPP2-water-record.gs'), 'function waterBuildingMatches_'],
    [path.join(root, 'validation', 'validate_deployment_smoke.mjs'), 'parsed.protocol !== \'https:\''],
    [path.join(root, 'validation', 'validate_deployment_smoke.mjs'), 'cursor did not terminate safely'],
  ];
  const missing = [];
  for (const [file, expected] of expectations) {
    const source = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
    if (!source.includes(expected)) missing.push(`${path.relative(root, file)}: ${expected}`);
  }
  const pass = missing.length === 0;
  results.push({ name: 'repository source inspection', result: pass ? 'PASS' : 'FAIL',
    evidenceClass: 'VERIFIED_BY_REPOSITORY_INSPECTION', checked: expectations.length, missing });
  console.log(`${pass ? 'PASS' : 'FAIL'} repository source inspection [VERIFIED_BY_REPOSITORY_INSPECTION]`);
  return pass;
}

let ok = inspectRepositoryContracts();
for (const [name, command, args] of checks) ok = run(name, command, args) && ok;
if (process.env.ANF3_RUN_LOCAL_ARTIFACTS === '1') {
  ok = run('seven-route document artifacts', python, ['validation/validate_document_artifacts.py']) && ok;
  ok = run('seven-route browser smoke', 'node', ['validation/validate_browser_smoke.mjs']) && ok;
} else {
  for (const name of ['seven-route document artifacts', 'seven-route browser smoke']) {
    results.push({ name, result: 'NOT_TESTED', evidenceClass: 'NOT_TESTED', reason: 'requires an explicitly running local service' });
    console.log(`NOT TESTED ${name} [NOT_TESTED]`);
  }
}

/* External gates are never silently converted into local PASS results. They
   remain visible in the same report while the deterministic local verdict can
   still be consumed by CI. */
for (const name of ['live Apps Script deployment', 'copied installed release', 'Owner visual sign-off']) {
  if (!results.some((item) => item.name === name)) {
    results.push({ name, result: 'NOT_TESTED', evidenceClass: 'NOT_TESTED', externalOnly: true,
      reason: 'requires Owner-controlled deployment, target-machine copy-down, or visual sign-off' });
    console.log(`NOT TESTED ${name} [NOT_TESTED]`);
  }
}

const report = { generatedAt: new Date().toISOString(), localOnly: true, results,
  summary: { pass: results.filter((item) => item.result === 'PASS').length,
    fail: results.filter((item) => item.result === 'FAIL').length,
    notTested: results.filter((item) => item.result === 'NOT_TESTED').length,
    deterministicLocalPass: ok && results.filter((item) => !item.externalOnly)
      .every((item) => item.result === 'PASS') } };
fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(`report=${path.relative(root, reportPath).replaceAll(path.sep, '/')}`);
process.exitCode = ok ? 0 : 1;
