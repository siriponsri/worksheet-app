# LUNA IMPLEMENTATION REPORT

## Identity
- Task ID: ANF3-20260910-002
- Iteration: 10
- Status: IMPLEMENTATION_COMPLETE

## Files Changed
- `START-ANF3.bat`
- `google/app-scripts/RPP2-water-record.gs`
- `google/app-scripts/RPP2-air-record.gs`
- `apps/web/src/` (Records List, Fill-in, batch print, payload pagination, styles, and focused tests)
- `js/` (legacy EM, Compressed Air, and CV mappings/blank-value behavior)
- `server/pdf_server.py`
- `server/tests/test_pdf_server.py`
- `validation/` (launcher, legacy mapping, artifact, browser, deployment, and local-runner checks)
- `docs/OUTPUT.md`
- `validation/POST_DEPLOYMENT_VALIDATION_7.1v.md`

## Implementation Summary
- Launcher reuse now requires ANF3 status identity, running state, converter availability, and server folder identity; lock initialization is race-safe.
- Legacy CV/EM/Compressed Air mappings preserve authoritative aliases and leave absent laboratory values blank.
- React document payloads paginate at template capacity with self-contained page dictionaries.
- Local validators cover launcher negatives, legacy mappings, rollback fault paths, seven populated document routes/pages, strict deployment fixtures, and all browser print routes.
- `run_local_validation.mjs` is the single local gate and writes `output/validation-report.json`; Owner-only checks remain informational.
- Fixed the double-escaped whitespace regex in the active Water/Air Apps Script building tokenizers and added source-executed B10/B12/B16/Other regression coverage.
- Deployment smoke now continues through all scopes and aggregates failures instead of stopping at the first mixed-building response.

## Evidence Rechecked During Implementation
- Local PDF service `/api/status` returned `status=running`, `converterAvailable=true`, and the expected folders on port `8011`.
- Browser smoke used the local Vite app on port `5173`; no Apps Script endpoint or production data was contacted.
- Release identity is consistent: `VERSION.txt` and `RELEASE.txt` both report `7.1aa`.
- The Owner redeployed the corrected Water and Air source. The final aggregate read-only live smoke passed all 18 configured Water/Air/CV scopes with zero mixed-building or cursor failures.

## Tests / Commands Run
1. `$env:ANF3_RUN_LOCAL_ARTIFACTS='1'; $env:ANF3_ARTIFACT_SERVER='http://127.0.0.1:8011'; node validation/run_local_validation.mjs`
   - Result: PASS
   - Evidence: the latest Iteration 10 local gate result is recorded in `output/validation-report.json`; it includes repository-inspection, execution, and not-tested evidence classes.
2. `pnpm test`
   - Result: PASS - 15 files, 107 tests.
3. `pnpm check` and `pnpm build`
   - Result: PASS.
4. `py -3.11 -m pytest server/tests -q`
   - Result: PASS - 28 tests.
5. `git diff --check`
   - Result: PASS; only expected line-ending normalization warnings.
6. `ANF3_SMOKE_TIMEOUT_MS=60000 node validation/validate_deployment_smoke.mjs` with the configured Water/Air/CV `/exec` URLs
   - Result: PASS - 18 live read-only scopes.

## Artifacts Inspected
- `output/document-artifacts/manifest.json`: all seven routes produced non-empty DOCX/PDF pairs, route/template checks passed, and all rendered PDF pages were inspected.
- `output/playwright/`: all seven document routes and login/list/print interaction evidence passed.
- `output/validation-report.json`: machine-readable result and evidence-class report.

## Regression Checks
- Negative coverage passed for invalid ANF3 status, missing converter, lock initialization race, malformed legacy mappings, over-capacity pagination, strict Apps Script URL forms, repeated/unterminated cursors, mixed buildings, and rollback cleanup failure.
- No production Sheets, permission, or external document mutation occurred in this session. The Owner-controlled Apps Script redeploy was treated as an external prerequisite.

## Read-Only Live Smoke
- The aggregate validator completed all configured scopes. Water B10/B12/B16, Air B10/B12/B16, and all CV scopes passed schema/building checks.
- All Water (6), Air (8), and CV (4) scopes passed building isolation, response schema, pagination, and safe cursor termination after redeployment.
- Evidence class: `VERIFIED_BY_EXECUTION`; no production mutation was performed by this session.

## Diff Review
- Unrelated changes: NONE identified in the authorized task diff.
- Generated artifacts accidentally tracked: NONE; `output/`, `words/`, and `pdfs/` remain local validation outputs.
- Debug residue: NONE.
- Secrets/sensitive data: NONE.

## Known Limitations
- The remaining copied installed release and Owner visual sign-off checks are `NOT_TESTED` and are not represented as local PASS.
- `START-ANF3.bat` itself was not launched through an interactive target-machine copy; deterministic launcher source/model contracts passed.

## Unresolved Questions
- NONE for the local automation scope.

## Requested Next State
READY_FOR_ASTRA_AUDIT
