# Evidence Packet: ANF3-20260918-001

## Current Working Tree
- Uncommitted modifications in: START-SERVER.bat, apps/web/src/appData.test.ts, apps/web/src/appData.ts, server/activity_log.py, server/pdf_server.py, server/tests/test_pdf_server.py.
- Git status: 6 modified files, ~342 insertions / 206 deletions.
- Previous task (ANF3-20260910-002) is complete and archived in `.agent-bus/*_ANF3-20260910-002.*`.

## What Is Already Done
1. `pdf_server.py` now writes controlled artifacts to `ANF3_PROJECT_SHARE` under:
   - `words/<workflow>/<worksheetNo>.docx`
   - `pdfs/<workflow>/<worksheetNo>.pdf`
   - `manifests/<workflow>/<worksheetNo>/<worksheetNo>.json`
2. `create_pdf()` requires `_ensure_project_share()` and returns 503 if share unavailable.
3. `_load_pdf_metadata()` searches the Share for downloads/previews.
4. `_backup_artifacts()` / `_publish_manifest()` stage with `.part` files and rollback backups.
5. `activity_log.py` reads `ANF3_PROJECT_SHARE` and writes `activity-log.jsonl` there.
6. `appData.ts` removed combined `samplingMode=passive,active` from B10/B12/B16 em-air binder routes via `listRoute()` workaround.
7. Tests updated to expect new share paths.

## Verified Failures
`python -m pytest server/tests -q` → 3 failures, 30 passed.

1. `test_project_share_replacement_keeps_old_version_in_history`
   - Expects old nested path `pdfs/pw-prw/PW-26-0093/PW-26-0093.pdf`.
   - New code uses flat `pdfs/pw-prw/PW-26-0093.pdf`. Test must be updated.

2. `test_project_share_outage_does_not_leave_local_controlled_artifacts`
   - Asserts no files under `cache/` after 503.
   - Test fixture itself creates `cache/words` and `cache/pdfs`. Assertion is wrong for new fixture.

3. `test_project_share_replaces_corrupt_primary_for_same_content`
   - Corrupt PDF `%PDF-1.4 different\n%%EOF\n` passes `_is_valid_pdf()` and metadata pdfId matches.
   - `_share_entry_is_current()` does NOT verify the PDF/DOCX content hash against metadata, so it returns `cached=True` (HTTP 200) instead of regenerating (HTTP 201).

## Gaps Found by Inspection

### Hard-coded T: / shared path in product behavior
- `START-SERVER.bat:28` hard-codes `set "ANF3_PROJECT_SHARE=T:\AN_Share\ANF3\10_Documents\01-WORKSHEET_ANF3\worksheet"`.
- `server/pdf_server.py:52-55` defaults `PROJECT_SHARE_ROOT` to the same `T:\...` path.
- `server/activity_log.py:51-54` defaults `PROJECT_SHARE_ROOT` to the same `T:\...` path.
- `START-ANF3.bat` does NOT set or pass `ANF3_PROJECT_SHARE` to `START-SERVER.bat`.

### Launcher contract
- `START-ANF3.bat` starts `%APP_DIR%START-SERVER.bat` with `start ...`.
- `APP_DIR` is the share root when launched from the share, or `%LOCALAPPDATA%\...` in `/here` or fallback mode.
- The shared-storage root should be `set "ANF3_PROJECT_SHARE=%APP_DIR%"` in `START-ANF3.bat` before starting the server, then inherited by `START-SERVER.bat`.
- `START-SERVER.bat` should require `ANF3_PROJECT_SHARE` and fail clearly if missing.

### Concurrent multi-PC writes
- `activity_log.py` uses `threading.Lock()` — process-local only. Multi-PC append to same `activity-log.jsonl` on SMB can interleave.
- `pdf_server.py` uses `BACKUP_LOCK` and `DOCUMENT_GENERATION_LOCK` — both `threading.Lock()`, process-local only. Two PCs could race on the same worksheet metadata/DOCX/PDF.
- Need cross-process file locking for log append and per-worksheet document replacement.

### em-air root cause
- `appData.ts` binder definitions for B10/B12/B16 em-air previously carried `secondaryFilter: { samplingMode: ['passive', 'active'] }`.
- `listRoute()` joined arrays to `passive,active`, and `api.ts` sent `samplingMode=passive,active`.
- Local `google/app-scripts/RPP2-air-record.gs` accepts comma-separated values (`airFilterValues_`), but the **deployed** endpoint historically did not, causing empty/error responses.
- Existing fix removes the filter for B10/B12/B16 via `listRoute()` workaround and deletes the secondaryFilter from definitions.
- `other-air` still has the secondaryFilter, but `listRoute()` workaround also skips it for em-air.
- This is a pragmatic frontend workaround for a deployment limitation; it does not hide a data error because the Air endpoint still scopes by building.

### Frontend/runtime tests
- Node.js / pnpm are not available in the orchestrator shell, so `pnpm check/test/build` could not be run here. Luna must run them in an environment with Node.

### Validation scripts
- `validation/validate_document_artifacts.py` uses env `ANF3_ARTIFACT_SERVER` and writes to `output/document-artifacts`. No hard-coded share paths.
- `validation/validate_release.py` checks source files/assets; should still pass.

## Recommended Fix Order
1. Remove hard-coded `T:` defaults from `pdf_server.py` and `activity_log.py`; fail closed when `ANF3_PROJECT_SHARE` is unset/invalid.
2. Update `START-ANF3.bat` to set `ANF3_PROJECT_SHARE=%APP_DIR%` before starting server.
3. Update `START-SERVER.bat` to require `ANF3_PROJECT_SHARE` (inherited) and remove hard-coded path.
4. Fix `_share_entry_is_current()` to verify PDF and DOCX fingerprints against stored metadata (add artifact hashes to metadata).
5. Fix Python test failures caused by path changes and corrupt-PDF regression.
6. Add cross-process file locking for activity log append and per-worksheet document replacement.
7. Verify em-air test expectations remain consistent.
8. Run full validation gates and report anything NOT RUN.
