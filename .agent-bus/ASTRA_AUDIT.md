# ASTRA AUDIT

## Identity
- Task ID: ANF3-20260918-001
- Iteration: 1
- Verdict: PASS with noted external gates

## Acceptance Criteria
- [x] DOCX and PDF filenames are `<worksheetNo>.docx` and `<worksheetNo>.pdf`.
- [x] Both files persist on the configured shared drive under `words/<workflow>/` and `pdfs/<workflow>/`.
- [x] Hash/pdfId is used only for cache/change detection and conflict payloads.
- [x] GENERATE / NO_CHANGE / WORKSHEET_CONTENT_CONFLICT behavior is preserved.
- [x] Preview/download/print use the same generated artifact (verified download route).
- [x] No `T:` hard-coded in product behavior; shared root passed explicitly from launcher to server.
- [x] Local storage keeps only runtime/cache/temp/venv files.
- [x] Shared storage unavailability returns a clear actionable 503 error, no silent fallback.
- [x] Concurrent multi-PC writes addressed with cross-process file locking for logs and per-worksheet documents.
- [x] em-air document generation works with the correct route/template.
- [ ] Frontend TypeScript/build/test gates — NOT RUN (missing Node.js).
- [ ] Full seven-route document artifact inspection — NOT RUN (missing Poppler).

## Verification Reviewed
- `python -m pytest server/tests -q`: 33 passed, 0 failed.
- `python validation/validate_release.py`: PASS.
- `git diff --check`: PASS (line-ending warnings only).
- Local server smoke with configured share: PASS.
- em-air synthetic generation `AT-26-B10-9001`: PASS; files on share at `words/em-air/` and `pdfs/em-air/`.
- Download `/api/pdfs/<pdfId>/download`: PASS (200, ~1 MB PDF).
- Controlled conflict/replace/NO_CHANGE smoke: PASS.
- Share-unavailable smoke: `/api/status` 200 with `projectShareAvailable:false`; `/api/pdfs` 503 with actionable message.

## Findings
No blocking findings. The AO worker harness (opencode) was non-functional for this session, so evidence gathering and implementation were performed directly by the orchestrator. The changes are surgical and evidence-supported.

## Residual Risks
- Frontend gates (`pnpm check`, `pnpm test`, `pnpm build`, `validate_wiring.mjs`) were not executed because Node.js is not installed in this environment. They must be run before release.
- Full `validate_document_artifacts.py` seven-route PDF page inspection was not executed because Poppler (`pdfinfo`, `pdftoppm`, `pdftotext`) is not installed. The script was updated to read artifacts from the share and verified to reach that stage.
- Cross-process locking uses `msvcrt.locking` (Windows only). Non-Windows environments silently no-op; production is Windows.
- Real multi-PC concurrent write stress was not exercised; the locking contract was verified by code review and single-process smoke.

## Post-Audit Remediation (2026-09-18)
- [x] **B1** — `START-ANF3.bat` `/here` mode now requires an explicit `ANF3_PROJECT_SHARE` (env var or second argument); it no longer silently treats the local repo as durable storage. `START-SERVER.bat` double-backslash in share-existence check cleaned.
- [x] **B1** — Added `server/tests/test_launchers.py` with 5 regression tests validating `NORMAL`, `DEV`, `/here`, `/here with share`, and missing-share behavior.
- [x] **M1** — `_publish_manifest` in `server/pdf_server.py` now promotes DOCX and PDF first, then writes metadata last as the commit record. If metadata promotion fails, all promoted artifacts are rolled back so a torn set cannot be treated as current.
- [x] **M1** — Added `test_torn_artifact_set_is_detected_and_regenerated` verifying that metadata mismatch with DOCX/PDF hash triggers regeneration and that `WORKSHEET_CONTENT_CONFLICT` still protects against content changes.
- [x] **M2** — `activity_log.record()` now returns `(entry, reason)`; `/api/log` returns distinct 400/500/503 messages for unknown action, write failure, and share-unavailable states.
- [x] **M2** — Existing tests updated to match the new tuple return contract.

## Verification After Remediation
- `python -m pytest server/tests -q`: 39 passed, 0 failed.
- `python validation/validate_release.py`: PASS.
- `git diff --check`: PASS (line-ending warnings only).

## Final State
PASS with external gate reservations (Node.js and Poppler still unavailable in this environment).
