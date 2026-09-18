# CURRENT TASK

## Identity
- Task ID: ANF3-20260910-002
- Iteration: 10
- Planner: Astra
- Implementer: Luna

## User Goal
Complete the nine reported defects in the release the Owner opens: redesign all active React and legacy application pages as Records Café while retaining the physical binder core; restore Air/CA/WFI records and true Building scope; split Other by domain; add a real editable Fill-in layer before Print; and allow deliberate controlled replacement of conflicting CV documents.

## Skills Required Before UI Work
Read these project-local skills and all directly referenced guardrails before editing:
- `.agents/skills/web-design-reviewer/SKILL.md` and `references/visual-checklist.md`
- `.agents/skills/frontend-design/SKILL.md`
- `.agents/skills/typeui-fundamentals/SKILL.md`
- `.agents/skills/typeui-fundamentals/accessibility.md`
- `.agents/skills/typeui-fundamentals/spacing-principles.md`
- `.agents/skills/typeui-fundamentals/typography-principles.md`
- `.agents/skills/typeui-fundamentals/ui-principles.md`
- `.agents/skills/typeui-fundamentals/ux-principles.md`
- project `$anf3-debug`, `$anf3-document-pipeline`, and `$karpathy-guidelines`

Use installed skills as design/build/audit guidance. The TypeUI Café page returned HTTP 429 during Astra research; do not claim pixel study or copy it. Source of truth is the Owner-approved Records Café direction, `DESIGN.md`, and physical binder assets.

## Verified Current State
- Iteration 6 automated tests pass but Astra audit found seven blocking/major findings.
- React sends logical Building/type filters and defensively filters mixed-building summaries.
- Local Water/Air Apps Script supports filters; configured live deployments previously ignored Building and require Owner New Version deployment plus read-only proof.
- List lacks requested search/group/detail design and models errors globally.
- Other is one binder; no Other-CV binder exists.
- Print auto-renders; record detail has only blank-key fill fields.
- `/api/pdfs` fails closed on changed content but provides no controlled resolution.
- Raw record/payload keys can be rendered to users.

## Source-of-Truth Evidence
- Iteration 6 `.agent-bus/ASTRA_AUDIT.md` and actual working-tree diff.
- `DESIGN.md`, `design-assets/manifest.json`, `docs/CABINET_WORKFLOW_MATRIX.md`.
- React List/scope/group/document/print modules under `apps/web/src/`.
- local Water/Air Apps Script and `server/pdf_server.py` plus tests.
- authoritative templates and seven document routes in `AGENTS.md`.
- active legacy pages share `css/anf3-v7.css`; Games and `_archived/` are excluded.

## Execution Path
`START-ANF3.bat` → copied dist/config → binder/domain/building List → logical Apps Script search/get → scoped selection → Print preflight Fill-in draft → server-owned document payload/template → GENERATE/NO_CHANGE or confirmed replace → DOCX/PDF → exact List return.

## Required Changes

### 1. Records Café design system on active application surfaces
- Update `DESIGN.md` before component/CSS changes. Preserve shelf/binders, existing building colors, binder shapes/assets, route ownership, and Games freeze.
- Apply to all React routes and active legacy HTML; exclude Games, `_archived/`, diagnostic tools, and DOCX template layout.
- Direction: laboratory reading room / records café, not literal café decoration. Use paper/surface/wood/ink hierarchy, ruled finding-aid structure, and building-color binder markers. No generic card wall, glass, gradients, emoji icons, or decorative metrics.
- Use Maitree for restrained headings, IBM Plex Sans Thai for UI/body, IBM Plex Mono only for worksheet/code. Use local font assets and remove legacy runtime Google Fonts.
- Preserve dark mode and WCAG AA; verify 320/375/414/768/1024/1280/1366/1920 plus 125%/200% zoom.

### 2. Unified List as a readable registry
- Support URL state: `building`, `domain`, `workflow`, `q`, `from`, `to`, and `groupBy=building|work`; default Building → Domain → Work, while single-Building scope groups Domain → Work.
- Show worksheet, human workflow, exact source building, dates, status, product/sampling points, sample count, and CV method where present. Load full record only when Details opens.
- Present Details in human sections: General, Sampling, Media, Results, Approval. Never dump storage objects.
- Model loading/errors per workflow and keep successful groups visible.
- Keep server filtering plus defensive client Building filtering before display.
- Restrict selection to one compatible PDF route/workflow at a time; disable incompatible rows with explanation, make Select all group-compatible, clear/reconcile selection when scope changes, and preserve exact return query.

### 3. Restore and prove Air/CA/WFI data
- Add a cursor-aware read-only deployment smoke validator for PW/PRW, WFI/PUS, EM, and CA over applicable B10/B12/B16/Other routes. Verify every returned item matches Building and cursors terminate safely.
- Do not deploy. Provide exact Owner New Version steps for Water and Air, then require post-deploy smoke evidence and copied-release browser evidence before PASS.
- Keep logical API fields only; never add shard names to frontend requests/UI.

### 4. Split Other binders
- Replace combined Other with `Other-Water`, `Other-Air`, `Other-CA`, and `Other-CV`, all using the existing Other color/asset family and `building=Other`.
- Other-Water exposes PW/PRW and WFI/PUS; Other-Air exposes EM; Other-CA exposes CA/N2; Other-CV exposes Contact and Rinse routing.
- Preserve exact Building 11/19/unknown source text when available and OT numbering/storage compatibility.
- Update typed registry, shelf/List parity tests, `DESIGN.md`, cabinet matrix, manifest capacity metadata, and validators.

### 5. Print preflight Fill-in
- Stop automatic generation on `/print/...`. Add a closed-by-default desktop side drawer/mobile bottom sheet named `Fill in / Edit before print`.
- Select queued worksheet, prefill all template-printable header/sample/result fields, allow edits to existing values, and keep per-worksheet local drafts without mutating System DB.
- Lock worksheet/document identity, record key, domain/workflow/building, sample family/method/template route, sample count, and row order. Do not add/delete/reorder samples.
- Results accept blank, numeric text, `<1`, `TNTC`, and legacy text. Provide Reset to System DB, Cancel, dirty/stale state, validation, and explicit Generate preview.
- Draft changes invalidate preview and block Print/Download until regeneration.
- Define workflow-specific presentation/edit schemas; never derive visible labels from placeholder/storage keys.

### 6. Controlled replacement contract
- Conflict response code is `WORKSHEET_CONTENT_CONFLICT` with worksheet/workflow/requested PDF id and sorted existing PDF ids.
- Confirmed retry sends `regeneration.mode=replace`, requested id, and exact existing id set.
- Inside document lock, re-check identity/set, build DOCX/PDF/metadata in temporary paths, validate placeholders/conversion, atomically replace worksheet DOCX, then commit new PDF/metadata. Remove superseded PDF/metadata only after success.
- Owner policy: no revision archive. New metadata records regeneration time and superseded ids. Failed conversion leaves old artifacts usable.
- UI displays human-readable changed fields and requires explicit per-worksheet confirmation. Never silently overwrite.
- Cover `CV-26-B10-0001` Contact and `CVR-26-B16-0001` Rinse Membrane.

### 7. Prevent technical-language leakage
- English is primary. Map internal fields to user terms such as Average result, Result I, Membrane lot, Sampling point, and Test method.
- Never display `samplesJson`, `templatePayload`, placeholder names, serialized JSON, or raw aliases such as `resultAvg`, `result1`, `lotPMembrane`, `leftEM`. Preserve them internally.
- Render samples as workflow-aware rows/forms. Add DOM leakage tests across List, Details, Fill-in, Print, errors/empty/loading, and representative legacy pages.

### 8. Release identity and installed-app evidence
- Increment release identity after implementation, rebuild dist, and validate isolated copy-down plus application opened through `START-ANF3.bat`. Do not edit installed copy as the product fix.

## Must Preserve
- Apps Script schemas, logical API contracts, worksheet formats/history, CV Test-Method routing, template families/placeholders/layout, per-page header semantics, and `<worksheetNo>.docx/.pdf`.
- Missing data stays blank; never fabricate results, lots, tags, approvals, replicates, or dates.
- Existing user changes in the dirty worktree.
- No physical shard names in frontend.

## Must Not Do
- Do not deploy/reconfigure Apps Script or mutate production Sheets.
- Do not rename legacy contracts for cleanliness.
- Do not edit authoritative DOCX layout.
- Do not redesign Games, `_archived/`, or diagnostic tools.
- Do not claim live/visual/installed verification without execution.

## Verification Required
- Unit/integration: URL/grouping/filtering, mixed rows, partial failure, compatible selection, scope reset, exact return, Other routes, presentation schemas, forbidden-token scan, Fill drafts, and conflict states.
- Server: GENERATE, NO_CHANGE, conflict payload, invalid/stale confirmation, success, failed-conversion rollback, concurrency.
- Documents: all seven routes; cited CV conflicts; open DOCX/PDF, filenames, routes, no unresolved placeholders, visual correspondence.
- Browser: target widths/zoom, light/dark, keyboard/focus, reduced motion, loading/error/empty, drawer/sheet, dirty preview, conflict confirmation; save before/after screenshots and axe zero critical.
- Active legacy route smoke for representative menu/list/form/print per domain plus leakage scan.
- `pnpm test`, `pnpm check`, `pnpm build`, Python tests, launcher/Air/CV/non-game/style/asset checks, `git diff --check`, final diff/artifact/secret/debug review.
- Owner-only: Water/Air New Version deployment and post-deploy smoke; seven-route visual checklist.

## Definition of Done for This Task
- [ ] All nine issues pass through the copied Owner release.
- [ ] Records Café is cohesive across React and active legacy pages while binders remain core navigation.
- [ ] Air/CA/WFI live rows are proven after Owner deployment.
- [ ] Other has four domain binders with correct routes.
- [ ] Print Fill-in edits printable fields without changing System DB.
- [ ] Controlled replace resolves both cited CV conflicts without silent overwrite or partial failure.
- [ ] No internal JSON/key/placeholder language is visible in normal frontend states.
- [ ] Automated, browser, artifact, installed-release, and Owner gates are documented honestly.

## Known Risks / Stop Conditions
- Water/Air deployment is an Owner external action; Luna stops short of deployment.
- If active source/template/workbook evidence conflicts on laboratory meaning, return to Astra rather than guessing.
- If legacy redesign exposes incompatible duplicate runtime contracts, preserve behavior and report exact evidence before architectural replacement.

## Iteration 8 Correction Scope
Read `.agent-bus/ASTRA_AUDIT.md` in full before editing. Resolve F1–F10 without broadening the task. In particular, restore the confirmed CV Rinse mappings before any external deployment, make controlled replacement rollback-safe under injected commit failures, place Fill-in before generation in the actual Print queue, replace generic payload-key labeling with per-route schemas, complete the List URL/group/detail contract, expose both PW/PRW and WFI/PUS from Other-Water, and add the read-only deployment smoke validator.

Run the original Iteration 7 suites plus every Required re-test listed in the audit. Browser, installed-release, and seven-route artifact evidence must be produced after the code corrections. Live Apps Script deployment remains Owner-only and must not be performed by Luna.

## Verification Addendum (2026-09-11)
- The Iteration 8 implementation and Login addendum are present in the working tree.
- Local unit, TypeScript, build, server, browser, deployment-fixture, launcher, routing, style, security, and document-artifact checks have been rerun.
- The Login gate uses `[ชื่อ หรือ ชื่อเล่น]` and `[รหัสพนักงาน]`, follows the Records Cafe theme, and is centered at desktop/mobile widths without horizontal overflow.
- A hostile review found and fixed URL normalization dropping `groupBy=building`, and cache validation accepting non-empty invalid PDF bytes.
- Live Apps Script behavior is now verified read-only after the Owner redeployed; target-machine copy-down and Owner visual gates remain explicitly untested.

## Iteration 9 Automation Addendum (2026-09-11)

### User Goal
Replace the remaining Owner-only verification with detailed, repeatable automated tests wherever the repository can prove the behavior locally. Keep external deployment and production access read-only and report them separately rather than claiming them as automated.

### Verified Current State
- The latest hostile review confirms the existing happy-path suites do not prove launcher identity/converter health, lock initialization safety, legacy CV aliases, over-capacity React pagination, no-fabrication behavior, populated seven-route artifacts, all-route browser coverage, strict deployment URL/fixture coverage, or worst-case rollback cleanup.
- At the Iteration 9 handoff the working tree contained staged product changes and uncommitted Agent Bus files; the owner's later authorization permits committing all current files except `.gitignore`.

### Required Changes
- Harden `START-ANF3.bat` to accept only a valid ANF3 `/api/status` response with converter availability, including already-running services; make lock initialization race-safe and add deterministic launcher race/health tests.
- Restore active legacy CV mappings and aliases from the real templates; keep missing laboratory values blank in legacy EM/Compressed Air form and print paths; add executable contract tests.
- Split React document payloads at each authoritative template capacity and send self-contained `pages` dictionaries with header plus page samples; add 31/51-sample tests for affected routes and preserve the seven route contracts.
- Upgrade document artifact validation to use non-empty route-specific fixtures, prove sample/header mappings and every generated page, inspect all pages, and compare DOCX/PDF content without production data.
- Expand browser smoke to all seven document routes and document the deterministic request/DOM/accessibility evidence; strengthen deployment smoke with strict Google Apps Script `/exec` validation and complete local fixtures, including CV.
- Add rollback cleanup-failure fault coverage that exercises both remove and unlink failure paths and proves no `.rollback` sidecars or mixed artifact sets remain.
- Add one local automated verification entry point that runs the focused suites, writes a machine-readable report with command/result/evidence class, and makes Owner-only external checks informational.
- Reconcile `VERSION.txt`, `RELEASE.txt`, `STATUS.json`, `CURRENT_TASK.md`, `LOCK.json`, and the Luna report before handoff. Do not claim copied-release, live deployment, or visual sign-off without execution.

### Must Preserve
- Logical Apps Script contracts, worksheet identity, authoritative DOCX layout/placeholders, per-page self-contained server semantics, and blank missing values.
- No production Sheets mutation, Apps Script deployment, or external document mutation.

### Verification Required
- Run the original focused regressions plus the new automated entry point in a clean local/test fixture environment.
- Prove negative cases: invalid ANF3 status, missing converter, lock initialization race, malformed legacy mappings, over-capacity pagination, populated placeholder mismatch, strict URL rejection, and rollback cleanup failure.
- Record live deployment/copy-down/visual checks as `NOT RUN` unless actually executed; they must not be represented as automated PASS.

### Definition of Done for Iteration 9
- [x] The automated entry point exits non-zero on each injected negative case and zero on the complete deterministic local suite.
- [x] The report clearly separates `VERIFIED_BY_EXECUTION`, `VERIFIED_BY_REPOSITORY_INSPECTION`, and `NOT_TESTED` external evidence.
- [x] No remaining product-code blocker from the hostile review is left untested or unfixed.

## Iteration 9 Revalidation Addendum (2026-09-11)

- The full local gate was rerun with the current-worktree PDF service on port `8011`: `23 PASS`, `0 FAIL`, and `3 NOT_TESTED`; `deterministicLocalPass=true`.
- The machine-readable report now contains all three evidence classes: `VERIFIED_BY_REPOSITORY_INSPECTION`, `VERIFIED_BY_EXECUTION`, and `NOT_TESTED`.
- The three `NOT_TESTED` entries are external-only checks: live deployment, copied installed release, and Owner visual sign-off.
- A prior read-only live smoke found a deployment mismatch: Water `pw-prw` with `building=Other` returned a `Building 12` item. The checked-in source excludes B12 from `Other` at `google/app-scripts/RPP2-water-record.gs:826`.
- No production deployment, Sheet mutation, permission change, or external document mutation was performed.
- The prior mismatch was resolved by the Owner redeployment and is closed by the final aggregate smoke below.

## Iteration 10 Root-Cause Correction Addendum (2026-09-11)

- The final aggregate live read-only smoke completed all 18 configured Water, Air, and CV scopes with zero failures.
- Root cause was proven in the active Apps Script source: Water and Air tokenizers used a double-escaped whitespace class (`[\\s_.-]+`), so values such as `Building 12` were classified as `Other`.
- Corrected `google/app-scripts/RPP2-water-record.gs` and `google/app-scripts/RPP2-air-record.gs` to use the real whitespace regex and added source-executed matcher regression tests.
- The Owner redeployed the corrected Water and Air source using the existing `/exec` URLs; post-deploy behavior matches the source-executed matcher tests.
- No production Sheet mutation, permission change, or external document mutation was performed by this session.

### Handoff State
ASTRA_AUDIT_PASS
