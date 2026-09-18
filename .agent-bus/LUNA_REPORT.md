# LUNA IMPLEMENTATION REPORT

## Identity
- Task ID: ANF3-20260918-001
- Iteration: 1
- Status: IMPLEMENTATION_COMPLETE — audit finding remediation applied

## Files Changed
- `START-ANF3.bat` — captures `SHARE_ROOT=%~dp0` and passes `ANF3_PROJECT_SHARE=%SHARE_ROOT%` to the server.
- `START-SERVER.bat` — requires inherited `ANF3_PROJECT_SHARE`; warns and continues if share unreachable (read-only UI stays up); never hard-codes `T:`.
- `server/pdf_server.py`:
  - Removed hard-coded `T:\...` default for `PROJECT_SHARE_ROOT`.
  - Added `wordSha256`/`pdfSha256`/`wordSize`/`pdfSize` to generated metadata.
  - `_share_entry_is_current()` now verifies artifact fingerprints against metadata, so corrupt/different files are regenerated instead of falsely cached.
  - Added `_lock_file_handle()`, `_unlock_file_handle()`, and `_worksheet_file_lock()` for cross-process locking on a per-worksheet lock file.
  - Wrapped `create_pdf()` worksheet-critical section with the cross-process lock.
- `server/activity_log.py`:
  - Removed hard-coded `T:\...` default for `PROJECT_SHARE_ROOT`.
  - Added `_lock_file()`/`_unlock_file()` using `msvcrt.locking` (Windows) with no-op fallback.
  - `record()` returns `None` when no log path is configured; write is file-locked, flushed, and fsync'd.
- `server/tests/test_pdf_server.py`:
  - Updated replacement history path to new flat `pdfs/<workflow>/<worksheetNo>.pdf` layout.
  - Updated outage test to assert no files (rather than no directories) under the local cache.

## Proven Root Causes
1. **Hard-coded shared path** — `START-SERVER.bat`, `pdf_server.py`, and `activity_log.py` all defaulted to `T:\AN_Share\...`, violating the requirement to support arbitrary drive letters/usernames/paths with spaces.
2. **False cache hit on corrupt PDF** — `_share_entry_is_current()` trusted metadata pdfId and a valid PDF header but never checked the actual file content, so a corrupt PDF with matching metadata was returned as `cached=True`.
3. **Stale test expectations** — tests still expected the old nested `pdfs/<workflow>/<ws>/<ws>.pdf` path and assumed the local cache directory should be completely absent after a share outage.
4. **Multi-PC race** — `threading.Lock()` only serializes within one process; two laboratory PCs could append to `activity-log.jsonl` or replace the same worksheet simultaneously.

## Tests / Commands Run
- `python -m pytest server/tests -q` → **PASS** (33 passed)
- `python validation/validate_release.py` → **PASS** (public source structural checks passed)
- `git diff --check` → **PASS** (only line-ending normalization warnings)
- Local server smoke (share configured) → **PASS**
  - `/api/status` returns `projectShareAvailable: true` and `converterAvailable: true`.
  - em-air generation for `AT-26-B10-9001` returns 201 and produces:
    - `words/em-air/AT-26-B10-9001.docx`
    - `pdfs/em-air/AT-26-B10-9001.pdf`
    - `manifests/em-air/AT-26-B10-9001/AT-26-B10-9001.json`
  - Download `/api/pdfs/<pdfId>/download` returns the PDF (200, ~1 MB).
- Controlled conflict smoke → **PASS**
  - First generate → 201 ready
  - Changed content → 409 `WORKSHEET_CONTENT_CONFLICT` with `existingPdfIds`
  - Confirmed replace → 201 ready
  - Identical content again → 200 `cached: true` (NO_CHANGE)
- Share-unavailable smoke → **PASS**
  - `/api/status` returns 200 with `projectShareAvailable: false`.
  - `/api/pdfs` returns 503 `Project share is unavailable; the worksheet was not saved`.
- `python validation/validate_document_artifacts.py` → executed, reached DOCX/PDF existence checks on the share, then failed at PDF page inspection because `pdfinfo`/`pdftoppm` (Poppler) are not installed.

## NOT RUN (with reason)
- `pnpm check`, `pnpm test`, `pnpm build` → **NOT RUN** — Node.js / pnpm are not installed or not in PATH in this environment.
- `node validation/validate_wiring.mjs --built` → **NOT RUN** — requires Node.js.
- `python validation/validate_document_artifacts.py` full seven-route inspection → **NOT RUN** — requires Poppler (`pdfinfo`, `pdftoppm`, `pdftotext`) in PATH.

## Generated Artifact Paths
- Intended share layout (verified by passing Python tests):
  - `words/<workflow>/<worksheetNo>.docx`
  - `pdfs/<workflow>/<worksheetNo>.pdf`
  - `manifests/<workflow>/<worksheetNo>/<worksheetNo>.json`
  - `activity-log.jsonl` (share root)
  - `.locks/<workflow>/<worksheetNo>.lock` (cross-process lock files)
- Local-only items retained:
  - `.venv`, `node_modules`, runtime cache under `ANF3_CACHE_DIR` (defaults to `%TEMP%\ANF3-Laboratory-Records-cache`)
  - Temporary DOCX/PDF during conversion

## Residual Risks
- Frontend TypeScript/build/test gates were not executed here due to missing Node.js; they must be run before release.
- `validate_document_artifacts.py` and real browser/download/print verification require a local server with an installed converter and a reachable shared drive.
- Cross-process locking uses `msvcrt.locking` on Windows only; non-Windows test environments silently no-op. This is acceptable because the production runtime is Windows.
- If the shared drive becomes unreachable after server start, document generation and log writes fail with 503; read-only browsing of System DB records remains possible.

## Audit Finding Remediation (2026-09-18)
- **B1 — `/here` launcher path discipline**
  - `START-ANF3.bat`: the `/here` developer mode now requires `ANF3_PROJECT_SHARE` to be provided explicitly (environment variable or second argument). It no longer silently uses the local repo directory as durable storage.
  - `START-SERVER.bat`: cleaned the double trailing backslash in the share-existence check.
  - Added `server/tests/test_launchers.py` with 5 regression tests covering `NORMAL`, `DEV`, `/here`, `/here with share`, and missing-share behavior.
- **M1 — Torn document publication**
  - Refactored `server/pdf_server.py::_publish_manifest()` to classify artifacts by `kind` (`docx`, `pdf`, `metadata`).
  - DOCX and PDF are promoted first; metadata is promoted last as the commit record.
  - If metadata promotion fails, all promoted artifacts (DOCX/PDF/metadata) are removed and backups are restored, preventing a torn set from being treated as the current worksheet version.
  - Added `test_torn_artifact_set_is_detected_and_regenerated` in `server/tests/test_pdf_server.py`.
- **M2 — `/api/log` error clarity**
  - Changed `server/activity_log.py::record()` to return a tuple `(entry, reason)` where `reason` is `None`, `'UNKNOWN_ACTION'`, `'SHARE_UNAVAILABLE'`, or `'WRITE_FAILED'`.
  - Updated `/api/log` route in `server/pdf_server.py` to return distinct HTTP status codes and messages for each failure reason (400 unknown action, 500 write failure, 503 share unavailable).
  - Updated existing `activity_log.record` monkeypatches in tests to return the new tuple contract.

## Verification After Remediation
- `python -m pytest server/tests -q` → **PASS** (39 passed, 0 failed)
- `python validation/validate_release.py` → **PASS**
- `git diff --check` → **PASS** (line-ending warnings only)

## Owner Deployment Steps
1. Ensure the shared release folder contains the updated `START-ANF3.bat` and `START-SERVER.bat`.
2. Each PC continues to double-click `START-ANF3.bat` in the shared release folder.
3. `START-ANF3.bat` now sets `ANF3_PROJECT_SHARE` to its own directory and starts the server.
4. `START-SERVER.bat` inherits the variable and refuses to start if it is missing.
5. Generated DOCX/PDF and activity logs will land on the share under `words/`, `pdfs/`, and `activity-log.jsonl`.
6. Do not copy changes to the live Shared Release until frontend gates are also green.
