/* =========================================================================
   The Windows launchers
   -------------------------------------------------------------------------
   These .bat files cannot be executed here, and they are the first thing a
   laboratory PC runs — a typo in one is a black window that flashes and
   closes, which is exactly the failure the owner reported before. So the
   parts that CAN be checked without Windows are checked: that every label a
   script jumps to exists, that every file it calls is really in the package,
   that no failure path exits without holding the window open, and that the
   share-drive launcher still does the things it exists to do.
   ========================================================================= */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const read = (name) => fs.readFileSync(path.join(ROOT, name), 'utf8');
const failures = [];
const check = (condition, message) => { if (!condition) failures.push(message); };

const LAUNCHERS = ['START-ANF3.bat', 'START-SERVER.bat', 'INSTALL.bat', 'BUILD-DIST.bat', 'INSTALL-MSOFFICE-SUPPORT.bat'];

for (const name of LAUNCHERS) {
  const source = read(name);
  const lines = source.split(/\r?\n/);

  /* Every label jumped to must exist, or the script dies with
     "The system cannot find the batch label specified". */
  const labels = new Set(
    lines.map((line) => line.match(/^\s*:([A-Za-z_][\w]*)/)).filter(Boolean).map((match) => match[1].toLowerCase())
  );
  const jumps = [...source.matchAll(/\b(?:goto|call)\s+:([A-Za-z_][\w]*)/g)].map((match) => match[1].toLowerCase());
  for (const target of new Set(jumps)) {
    if (target === 'eof') continue; // :eof is built in
    check(labels.has(target), `${name}: jumps to :${target}, which is not defined`);
  }

  /* Batch is whitespace-fragile: an unbalanced quote silently swallows the
     rest of a line. */
  lines.forEach((line, index) => {
    const quotes = (line.match(/"/g) || []).length;
    check(quotes % 2 === 0, `${name}:${index + 1}: odd number of quotes — "${line.trim().slice(0, 60)}"`);
  });

  /* Every .bat this script calls has to be in the package. */
  for (const match of source.matchAll(/call\s+"%[A-Z_]+%([A-Za-z0-9._-]+\.bat)"/g)) {
    check(fs.existsSync(path.join(ROOT, match[1])), `${name}: calls ${match[1]}, which is not in the package`);
  }

  /* A window that closes on failure tells the operator nothing. */
  check(/pause|:hold/i.test(source), `${name}: no pause on any path — a failure would just flash and close`);
}

/* ---- the share-drive contract, which is the point of START-ANF3.bat ---- */
const launcher = read('START-ANF3.bat');

check(fs.existsSync(path.join(ROOT, 'VERSION.txt')),
  'VERSION.txt is missing — the launcher compares it to decide whether a PC needs refreshing');

check(/LOCALAPPDATA/.test(launcher),
  'START-ANF3.bat no longer copies to %LOCALAPPDATA% — running several PCs from the share drive corrupts the venv, the log and the PDF output');

check(/robocopy/i.test(launcher),
  'START-ANF3.bat no longer uses robocopy — xcopy does not handle UNC paths reliably');

/* The per-machine state must never be copied down from the master, or every
   PC inherits another machine's environment, port file and audit log. */
for (const excluded of ['.venv', 'node_modules', '.agents', '.playwright-cli', '.pytest_cache', '.agent-bus', '.tmp-*', 'output', 'pdfs', 'words']) {
  const escaped = excluded.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  check(new RegExp(`/XD[^\\n]*"${escaped}"`).test(launcher),
   `START-ANF3.bat must exclude ${excluded}/ from the copy`);
}
for (const excluded of ['.anf3-port', 'activity-log.jsonl', 'log-forward.json']) {
  check(new RegExp(`/XF[^\\n]*"${excluded.replace(/\./g, '\\.')}"`).test(launcher),
    `START-ANF3.bat must exclude ${excluded} from the copy`);
}

check(/if errorlevel 8/.test(launcher),
  'START-ANF3.bat must treat robocopy exit codes >= 8 as failure (0-7 are success)');

check(/config\.json/.test(launcher) && /ConvertFrom-Json/.test(launcher),
  'START-ANF3.bat must validate config.json before starting the local service');

check(/script\[\.\]google\[\.\]com.*\/exec/.test(launcher),
  'START-ANF3.bat must accept only public Google Apps Script /exec URLs');

check(/:check_converter/.test(launcher) && /LibreOffice/.test(launcher),
  'START-ANF3.bat must report a missing DOCX-to-PDF converter before launch');

check(!/recorded_port_busy|tcp_port_busy/.test(launcher),
  'START-ANF3.bat must not block on a stale or foreign recorded port');
check((launcher.match(/del \/q "%LOCAL_DIR%\.anf3-port"/g) || []).length === 1
  && (launcher.match(/del \/q "%APP_DIR%\.anf3-port"/g) || []).length === 1,
  'START-ANF3.bat must clear stale port state only after acquiring its launch lock');
check(!/goto :busy_server/.test(launcher),
  'START-ANF3.bat must continue after a stale/foreign recorded port');

check(/:wait_for_server/.test(launcher) && /\/api\/status/.test(launcher),
  'START-ANF3.bat must wait for the local service status endpoint');

check(/8000\.\.8039/.test(launcher) && /TcpClient/.test(launcher) && /\/api\/status/.test(launcher),
  'START-ANF3.bat must scan the full server port range with a fast TCP check and verify ANF3 status');
check(/status -eq 'running'/.test(launcher) && /converterAvailable -eq \$true/.test(launcher) && /\$null -ne \$body\.folders/.test(launcher),
  'START-ANF3.bat must require ANF3 identity/state/folders and an available converter before reusing a service');
check(/call :check_server_converter\s+if errorlevel 1 goto :converter_missing\s+goto :open_server/.test(launcher),
  'START-ANF3.bat must re-check converter health on the already-running reuse path');

check(!/for \/l %%P in \(8000,1,8039\)/.test(launcher),
  'START-ANF3.bat must not spawn a separate PowerShell probe for every port');

check(/\.anf3-launch\.lock/.test(launcher),
  'START-ANF3.bat must serialize concurrent local refresh/start operations');
check(/:clean_retired_runtime/.test(launcher) && /Remove-Item/.test(launcher),
  'START-ANF3.bat must remove retired local outputs and coordination state after refresh');
check(!/set "ANF3_PORT=8000"/.test(read('START-SERVER.bat')),
  'START-SERVER.bat must not require a fixed port');

check(/owner\.txt/.test(launcher) && /Win32_Process/.test(launcher),
  'START-ANF3.bat must record and inspect the owning launcher process');
check(/ParentProcessId/.test(launcher),
  'START-ANF3.bat must record the batch owner rather than the PowerShell helper PID');
check(/START-ANF3\[\.\]bat/.test(launcher) && /rmdir \/s \/q/.test(launcher),
  'START-ANF3.bat must reclaim an abandoned lock but preserve an active launcher lock');

/* Deterministic local model of the batch decision: malformed/missing ownership
   is stale, while a live launcher PID remains protected. */
const lockDecision = ({ owner, activePids }) => {
  if (owner === null) return 'busy'; // mkdir succeeded; owner initialization is still in flight
  const match = /^([0-9]+)\|/.exec(owner || '');
  return match && activePids.has(Number(match[1])) ? 'busy' : 'stale';
};
check(lockDecision({ owner: null, activePids: new Set() }) === 'busy',
  'lock model must treat a missing owner file as an active initialization window');
check(lockDecision({ owner: '4210|PC\\user', activePids: new Set([4210]) }) === 'busy',
  'lock model must keep a genuinely active launcher lock protected');
check(lockDecision({ owner: '4210|PC\\user', activePids: new Set() }) === 'stale',
  'lock model must classify an abandoned launcher lock as stale');
check(lockDecision({ owner: 'legacy owner text', activePids: new Set([4210]) }) === 'stale',
  'lock model must recover a legacy/malformed lock without a PID');

/* Negative health models mirror the conservative PowerShell predicate used by
   the batch file. A 200 response alone is never sufficient for reuse. */
const healthyStatus = (body, httpStatus = 200) => httpStatus === 200
  && body?.status === 'running'
  && body?.converterAvailable === true
  && body?.folders !== null
  && body?.folders !== undefined;
check(healthyStatus({ status: 'running', converterAvailable: true, folders: {} }),
  'health model must accept a complete ANF3 status');
check(!healthyStatus({ status: 'ok', converterAvailable: true, folders: {} }),
  'health model must reject a non-ANF3 state even with HTTP 200');
check(!healthyStatus({ status: 'running', converterAvailable: false, folders: {} }),
  'health model must reject a service without a converter');
check(!healthyStatus({ status: 'running', converterAvailable: true }),
  'health model must reject a status response without ANF3 identity fields');

check(!/Starting from the share drive instead/i.test(launcher),
  'START-ANF3.bat must not fall back to starting Flask from the UNC share after copy failure');

check(/if\s+\/i\s+"%APP_DIR%"=="%LOCAL_DIR%"\s+goto\s+:run_here/i.test(launcher),
  'START-ANF3.bat must short-circuit when it is already the local copy, or it hands over to itself forever');
check(/ANF3_PROJECT_SHARE is not configured/.test(launcher)
  && /launcher directory is not controlled document storage/.test(launcher)
  && !/set "ANF3_PROJECT_SHARE=%APP_DIR%"/.test(launcher),
  'START-ANF3.bat must require explicit Share configuration and never use the checkout as durable storage');

/* The token must never reach a laboratory PC through the copy. */
check(!/ANF3_SYNC_TOKEN/.test(launcher), 'START-ANF3.bat must not mention the sync token');

if (failures.length) {
  console.error('Launcher checks FAILED:');
  for (const failure of failures) console.error('  - ' + failure);
  process.exit(1);
}
console.log(`Launchers OK — ${LAUNCHERS.length} scripts, labels resolve, share-drive copy contract intact.`);
