# CURRENT TASK

## Identity
- Task ID: ANF3-20260918-001
- Iteration: 1
- Planner: Astra
- Implementer: Luna
- Status: PLANNING

## User Goal
Fix three release-blocking issues in the ANF3 Laboratory Records local/shared document pipeline:

1. **DOCX/PDF persistence and filenames** — successful generation must persist both `<worksheetNo>.docx` and `<worksheetNo>.pdf`; worksheetNo is the durable/external identity; hash/pdfId remains internal for cache/change detection only; preserve GENERATE / NO_CHANGE / WORKSHEET_CONTENT_CONFLICT behavior; never silently overwrite changed controlled documents; preview/download/print must use the same generated artifact.

2. **Move durable storage to Shared Drive** — keep local only `.venv`, Python/runtime dependencies, frontend/runtime/cache, and temporary conversion files. Store on Shared Drive only generated DOCX, generated PDF, activity/operator/print/download logs, and other durable operational logs. Prefer one explicit shared-storage-root contract passed from `START-ANF3.bat` to the local Flask server. Do not hard-code `T:` in product behavior. Must work with different Windows usernames, paths containing spaces, and different mapped drive letters. If shared storage is unavailable, do not silently fall back to LOCALAPPDATA for controlled files/logs; return a clear actionable error; keep safe read-only functionality available where possible. Check concurrent multi-PC writes, especially logs and controlled documents.

3. **Fix Air Sampling / em-air not loading** — expected contract: workflow `em-air`, domain `air`, PDF route `em-air`, template `templates/em-template.docx`. Reproduce first. Trace appData/App.tsx → api.ts → Air search/get → selected record → documentPayload → batchPrint → Flask. Compare with a working workflow such as compressed-air. Find the first failing boundary. Do not hide the error or fabricate data.

## Work Directory
`C:\Users\siripon.sri\Desktop\my_project\worksheet` only.

## Shared Release
`T:\AN_Share\ANF3\10_Documents\01-WORKSHEET_ANF3\worksheet` is the target shared root, but must not be hard-coded in product behavior.

## Local Runtime
`C:\Users\siripon.sri\AppData\Local\ANF3-Laboratory-Records`.

## Constraints
- Do not edit the local runtime copy as the source fix.
- Do not deploy or modify production Google Sheets / Apps Script.
- Use synthetic/test data only.
- Evidence-first debugging: reproduce → trace → prove root cause → smallest fix → retest.
- No fabrication of results, control values, media lots, equipment IDs, dates, tags, replicates, or approvals.

## Required Inspection Before Editing
- `AGENTS.md`
- `START-ANF3.bat`
- `START-SERVER.bat`
- `INSTALL.bat`
- `server/pdf_server.py`
- `server/activity_log.py`
- `apps/web/src/appData.ts`
- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `apps/web/src/documentPayload.ts`
- `apps/web/src/recordPolicy.ts`
- `server/tests/test_pdf_server.py`
- `validation/validate_document_artifacts.py`
- `validation/validate_release.py`

## Definition of Done
- [ ] DOCX and PDF filenames are `<worksheetNo>.docx` and `<worksheetNo>.pdf`.
- [ ] Both files persist on the configured shared drive under `words/<workflow>/` and `pdfs/<workflow>/`.
- [ ] Hash/pdfId is used only for cache/change detection and conflict payloads.
- [ ] GENERATE / NO_CHANGE / WORKSHEET_CONTENT_CONFLICT behavior is preserved.
- [ ] Preview/download/print use the same generated artifact.
- [ ] No `T:` hard-coded in product behavior; shared root is passed explicitly from launcher to server.
- [ ] Local storage keeps only runtime/cache/temp/venv files.
- [ ] Shared storage unavailability returns a clear actionable error, no silent fallback.
- [ ] Concurrent multi-PC log writes and controlled-document replacements are safe.
- [ ] `em-air` list/detail/document generation works with the correct route/template.
- [ ] No regression in Water, WFI/PUS, Compressed Air, CV Contact, CV Rinse Pour, CV Rinse Membrane.
- [ ] All required validation gates pass; anything that cannot run is reported as `NOT RUN` with reason.

## Verification Gates
1. `pnpm check`
2. `pnpm test`
3. `pnpm build`
4. `python -m pytest server/tests -q`
5. `node validation/validate_wiring.mjs --built`
6. `python validation/validate_document_artifacts.py`
7. `python validation/validate_release.py`
8. `git diff --check`
9. Local runtime executes with shared storage root reaching Flask.
10. Synthetic EM files exist on Shared Drive as `words\em-air\<worksheetNo>.docx` and `pdfs\em-air\<worksheetNo>.pdf`.
11. Identical content ⇒ NO_CHANGE/reuse; changed content ⇒ controlled conflict.
12. Logs stored on Shared Drive; concurrent log writes safe.

## Stop Conditions
- If active source/template/workbook evidence conflicts on laboratory meaning, return to Astra rather than guessing.
- If shared storage is unavailable, do not silently fall back to LOCALAPPDATA for controlled files/logs.
- Do not deploy/reconfigure Apps Script or mutate production Sheets.
