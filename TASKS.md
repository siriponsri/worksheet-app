# ANF3 — Workflow Redesign, List Workspace, Controlled Backup, and CV Document Repair

## 0. Task Identity

**Task type:** Major cross-layer implementation
**Risk class:** T2 — High Risk / Cross-Layer
**Primary application:** Active React/Vite application under `apps/web/`
**Backend:** Local Flask document service
**Data source:** Google Sheets / Apps Script System DB
**Production data model:** Read-only from the browser

This task intentionally authorizes changes required to:

* redesign the active List workspace;
* redesign the record-selection → fill-in → preview → save/print workflow;
* extend local document/audit backup to a configurable project network share;
* diagnose and repair CV Contact / CV Rinse document replacement and PDF-generation failures.

This authorization does **not** authorize:

* mutation or deletion of production Google Sheet records;
* deployment of live Apps Script versions;
* modification of controlled DOCX artwork/layout unless a proven template defect requires owner approval;
* fabricated laboratory values;
* removal of existing compatibility contracts.

---

# 1. Primary User Goal

Rebuild the current ANF3 document workflow around an operator-friendly sequence:

```text
Folder / Binder
      ↓
Building + Workflow context
      ↓
List Dashboard
      ↓
Select worksheets using explicit ON/OFF controls
      ↓
Selected Work Queue
      ↓
Fill In
      ↓
Review
      ↓
PDF Preview
      ↓
Save / Print
      ↓
Local controlled artifacts
      ↓
Project Share backup
```

The operator must be able to work in either:

```text
INDIVIDUAL MODE
one worksheet
→ fill
→ preview
→ save / print

or

BATCH MODE
select many worksheets
→ bulk-safe fill
→ complete remaining worksheet-specific fields
→ render selected set
→ multi-page preview
→ save / print selected set
```

The application remains a **read-only laboratory-record viewer** with respect to the System DB.

Fill-in values are print-draft/document-generation values only and MUST NOT mutate source laboratory records.

---

# 2. Mandatory Execution Order

Implementation MUST NOT start with the visual redesign.

Use this sequence:

```text
P0  Baseline + reproduce document defects
 ↓
P1  Repair CV Contact / CV Rinse document pipeline
 ↓
P2  Define workflow state model
 ↓
P3  Implement List Dashboard + selection UX
 ↓
P4  Implement Fill-In Work Queue + single/batch workflow
 ↓
P5  Implement project-share backup
 ↓
P6  Full integration + visual audit + regression
```

The UI may be designed during P0/P1, but product-code integration of the new workflow should wait until document generation has a stable verified baseline.

---

# 3. P0 — Establish Baseline and Reproduce Current Defects

Before changing document-generation code:

1. inspect `AGENTS.md`;
2. inspect `git status` and current diff;
3. identify the active execution path;
4. identify representative non-production fixtures;
5. run the smallest relevant tests;
6. reproduce each reported failure separately.

Required reproductions:

### R1 — CV Contact Plate

Determine whether the failure occurs at:

```text
record retrieval
→ route normalization
→ payload construction
→ placeholder mapping
→ DOCX replacement
→ unresolved-placeholder validation
→ Word→PDF conversion
```

Inspect the real `cv-contact-template.docx`, including relevant Word XML parts.

Do not normalize or rename placeholders based on assumption.

Pay particular attention to known historical placeholder forms such as:

```text
<samplingTime >
```

including whitespace and Word run splitting.

### R2 — CV Rinse Pour Plate

Verify the complete route:

```text
CV record
→ Test-Method = POUR_PLATE
→ cleaning-validation-rinse-pour
→ PW/PRW controlled template
→ CV-owned payload mapping
→ DOCX
→ PDF
```

Required mapping behavior:

```text
source Result
→ resultAvgNN

result1NN = blank unless real source replicate exists
result2NN = blank unless real source replicate exists
```

Do not manufacture plate replicates.

### R3 — CV Rinse Membrane Filtration

Verify independently:

```text
CV record
→ Test-Method = MEMBRANE_FILTRATION
→ cleaning-validation-rinse-membrane
→ WFI/PUS-shaped template
→ resultNN
→ DOCX
→ PDF
```

Do not map the membrane result to `resultAvgNN`.

### P0 Deliverable

Create evidence showing for each defect:

```text
REPRODUCED
ROOT CAUSE PROVEN
or
NOT REPRODUCED
```

Do not fix a guessed cause.

---

# 4. P1 — Repair the CV Document Pipeline

Repair the smallest proven cause(s) from P0.

The following contracts MUST remain intact:

* `Test-Method` remains authoritative for CV Rinse routing.
* Contact, Rinse Pour, and Rinse Membrane remain distinct logical PDF routes.
* Pour Plate continues to reuse the approved PW/PRW template family.
* Membrane continues to reuse the approved WFI/PUS template family.
* CV document identity remains the CV/CVR worksheet number.
* missing laboratory values remain blank.
* page dictionaries remain self-contained.
* source System DB records remain read-only.
* existing `409 WORKSHEET_CONTENT_CONFLICT` behavior must not be bypassed.

### P1 Acceptance

For representative fixtures:

```text
CV Contact
CV Rinse Pour
CV Rinse Membrane
```

all must produce:

* a non-empty DOCX;
* correct route/template;
* correctly replaced expected placeholders;
* no unexpected unresolved controlled placeholder;
* non-empty, openable PDF;
* PDF visually corresponding to the generated DOCX;
* correct worksheet-based user-facing identity.

Actual generated artifacts MUST be inspected, not only unit tests.

---

# 5. P2 — Introduce an Explicit Operator Workflow State

Do not build the new UI from scattered React booleans.

Create or establish one coherent workflow state model representing:

```text
BROWSING
SELECTING
FILLING
READY
RENDERING
PREVIEWING
COMPLETED
PARTIAL_FAILURE
```

The model must track at least:

```text
current building
current workflow/binder
visible records
selected worksheet IDs
per-worksheet fill status
local print-draft values
render status
preview artifacts
failure reason per worksheet
```

Selection must survive:

* opening/closing worksheet details;
* entering a Fill-In screen;
* returning from an individual worksheet;
* PDF preview;
* recoverable render failure.

Changing to another binder/workflow may clear selection only through explicit predictable behavior.

Do not store source-record mutations.

---

# 6. P3 — Completely Redesign the List Page

The existing List page may be replaced visually and structurally.

The new page is an **operational dashboard**, not a generic SaaS dashboard and not a wall of decorative cards.

## Entry Context

The operator has already selected a Folder/Binder.

Therefore the List page opens already scoped by:

```text
Building
+
Workflow
```

Example:

```text
Building 16
Cleaning Validation
```

The selected folder/binder context must remain obvious without repeatedly displaying redundant metadata everywhere.

## List Dashboard

The page should prioritize rapid scanning.

Show the highest-value information directly, such as:

* worksheet number;
* date;
* workflow/type;
* sampling/product/location information where relevant;
* current readiness/fill state;
* concise result/status metadata where safe and useful.

Secondary/raw information must be hidden behind:

```text
Details
```

or an equivalent expandable disclosure.

The collapsed state must remain useful by itself.

## Worksheet Selection

Do NOT use row-click as the primary selection action.

Every worksheet has an explicit iOS-style ON/OFF control.

Conceptually:

```text
○ OFF    not included in work set

● ON     included in work set
```

Implementation must remain accessible:

* visible text or accessible label;
* keyboard operable;
* not color-only;
* sufficiently large pointer target;
* semantic switch/checkbox behavior.

Opening `Details` must not change selection.

Selecting a worksheet must not unintentionally open details.

## Selection Command Area

When worksheets are selected, show a restrained persistent action area containing at least:

```text
N selected
Clear
Continue to Fill In
```

Provide select-all-current-results only if its scope is unmistakable.

Never make a user guess whether “all” means:

```text
visible page
filtered result set
entire System DB
```

## Visual Direction

The page should feel:

```text
minimal
professional
operational
high information density
fast to scan
international
laboratory/instrument-like
```

Avoid:

* generic rounded SaaS card grids;
* excessive pills/badges;
* gradients used as decoration;
* glassmorphism;
* neon/space-tech styling;
* oversized hero content;
* unnecessary animation;
* hidden essential information;
* visual clutter.

Building color remains a navigation/orientation semantic, not a general status color.

---

# 7. P4 — Selected Work Queue and Fill-In Workflow

Selecting `Continue to Fill In` opens a dedicated work queue containing **only selected worksheets**.

Example:

```text
Selected Work — 6 worksheets

✓ CV-26-B16-0001   Ready
○ CV-26-B16-0002   Needs fill
○ CV-26-B16-0003   Needs fill
✓ CV-26-B16-0004   Ready
...
```

Each worksheet can be opened individually.

## Individual Fill-In

Opening one worksheet presents an explicit Fill-In workspace/modal/panel.

Use the existing print-draft policy where possible.

Fill-In MUST remain separate from System DB data.

After editing:

```text
Save draft
Save / Generate
Preview PDF
Print
```

The exact action naming may be refined during UX implementation, but state transitions must remain unambiguous.

Closing an unfinished worksheet must not silently discard changed draft values.

## Batch Fill

Provide a batch-fill mode for values that are genuinely safe to reuse across multiple selected worksheets.

**Do not make every fill field bulk-editable.**

A field may be batch-applied only when it is explicitly classified as bulk-safe.

Reuse or extend the existing print-fill allowlist rather than inventing a second independent field policy.

Worksheet-specific fields must remain worksheet-specific.

Never bulk-copy:

* microbiology results;
* sampling values;
* equipment identity;
* tags;
* worksheet identity;
* dates that differ per record;
* any laboratory value merely because another selected worksheet contains one.

The UI should make clear:

```text
Apply to selected worksheets
```

versus:

```text
Edit this worksheet only
```

## Completion Status

Every selected worksheet should have a status such as:

```text
Not reviewed
Draft changed
Ready
Rendered
Failed
```

The operator can continue through the queue without losing previous work.

---

# 8. Batch Preview / Save / Print

Reuse the existing controlled rendering path.

Do NOT create an independent “batch document generator” with different mapping logic.

For each selected worksheet:

```text
existing document payload
→ existing controlled PDF route
→ individual controlled DOCX/PDF
```

Then use the existing batch merge path for multi-page PDF presentation.

After rendering, show a full selected-set preview.

The operator must be able to:

```text
review all pages
exclude an accidentally selected worksheet where safe
save
print
return to fill-in
```

A failure in one worksheet must identify that worksheet and reason.

Where safe, successful worksheets should not be discarded merely because another selected worksheet failed.

The preview must preserve worksheet ordering.

Individual controlled DOCX/PDF artifacts remain individually identifiable even when a merged PDF is produced for convenience.

---

# 9. P5 — Local + Project Share Backup

Current local document generation remains primary.

Do not run the ANF3 application itself from the network share merely to achieve backup.

Introduce a **server-side backup service**.

The browser MUST NOT directly write SMB/network-share files.

## Backup Targets

Preserve local artifacts including:

```text
activity-log.jsonl
generated DOCX
generated PDF
relevant artifact metadata
```

Add a second configurable destination:

```text
ANF3 Project Share
```

The network path MUST be runtime configuration and MUST NOT be hardcoded into browser code.

Do not store credentials in browser-accessible configuration.

A safe conceptual layout is:

```text
<backup-root>/
  audit/
  words/
    <route>/
  pdfs/
    <route>/
  manifests/
```

Exact layout may follow existing repository conventions if a better established structure exists.

## Backup Trigger

After successful controlled artifact creation:

```text
local finalize
→ verify local artifact
→ attempt project-share backup
→ record backup result
```

Local generation MUST NOT be corrupted because the share drive is temporarily unavailable.

If the share is unavailable:

```text
LOCAL: SUCCESS
SHARE BACKUP: FAILED / PENDING
```

must be visible rather than falsely reporting complete backup.

Implement a deterministic retry mechanism such as a local pending-backup manifest/spool which can safely retry later.

Do not require an always-running cloud service.

## Backup Integrity

Before marking a backup successful, verify at minimum:

* destination exists after copy;
* non-zero size;
* expected worksheet identity;
* source and destination integrity using size/hash or equivalent deterministic validation.

Do not silently replace a different controlled artifact under the same worksheet identity.

Repeated backup of identical content should be idempotent.

If a legitimately regenerated worksheet has different content, preserve history/version evidence rather than silently destroying the previous backup.

## Audit Trail

Backup operations should themselves be attributable in the audit log using appropriate events such as:

```text
backup_succeeded
backup_failed
backup_retried
```

Do not misrepresent network backup as authentication or regulatory electronic-signature functionality.

---

# 10. P6 — Integration Acceptance

The new flow must work for representative records across all seven existing workflow routes:

```text
PW/PRW
WFI/PUS
EM Air
Compressed Air
CV Contact
CV Rinse Pour
CV Rinse Membrane
```

Minimum end-to-end scenarios:

### Scenario A — Single Worksheet

```text
Binder
→ List
→ toggle one worksheet ON
→ Fill In
→ Save
→ Preview
→ Print
→ local artifacts
→ project-share backup
```

### Scenario B — Batch

```text
Binder
→ List
→ select multiple
→ batch-safe fill
→ worksheet-specific completion
→ render
→ multi-page preview
→ save merged PDF
→ print
→ verify individual controlled artifacts
→ project-share backup
```

### Scenario C — Partial Failure

One worksheet fails document generation.

Expected:

* exact worksheet identified;
* reason shown;
* no fabricated artifact;
* other safe outputs remain usable;
* operator can return and correct/retry.

### Scenario D — Share Unavailable

Expected:

```text
local save succeeds
backup status reports failure/pending
no data loss
retry is possible
```

### Scenario E — CV Regression

Contact, Pour, and Membrane all produce valid controlled documents with their correct routing and mappings.

---

# 11. Required Verification

Run the smallest affected checks first and then adjacent regression.

At minimum:

```powershell
pnpm check
pnpm test
pnpm build

python -m pytest server/tests -q

node validation/test_cv_contract.mjs
node validation/test_worksheet_numbering.mjs
node validation/validate_wiring.mjs --built
python validation/validate_release.py

git diff --check
```

Run any additional existing interaction, styling, security, artifact, routing, or document validators affected by the actual diff.

For document work, tests alone are insufficient.

Inspect representative generated DOCX/PDF artifacts.

For the redesigned UI, verify real built-browser behavior at minimum on:

```text
desktop 1920×1200 class
narrow/mobile layout
keyboard navigation
light/dark where currently supported
```

Check console for errors.

---

# 12. Must Preserve

* Browser remains read-only against System DB.
* Building routing remains `B10`, `B12`, `B16`, `OT`.
* Existing worksheet identities are preserved.
* Controlled DOCX templates remain authoritative.
* CV method routing remains method-driven.
* Missing values remain blank.
* Existing artifact conflict protection remains active.
* Individual and batch document generation use the same controlled mapping/route logic.
* Existing audit attribution remains attribution, not authentication.
* No production Google Sheet mutation is required for this implementation.
* Frozen legacy pages remain untouched unless separately authorized.

---

# 13. Model Execution Policy

## Design Director — Kimi K3

Use Kimi K3 for **one concentrated design pass**, not the entire implementation.

Its responsibility:

```text
List Dashboard visual architecture
+
selection interaction
+
Fill-In work queue UX
+
single/batch workflow
+
responsive behavior
```

Kimi should inspect the existing active UI/design rules and produce a concrete implementation-ready visual/interaction specification.

Kimi should NOT spend expensive context on repetitive tests, grep loops, or document-pipeline debugging.

Recommended maximum:

```text
1 initial design pass
+
1 visual critique pass after implementation
```

## Primary Implementer — GPT-5.6 Luna

Luna owns the implementation across P0–P6.

Use Luna for:

* evidence-driven debugging;
* React state/workflow implementation;
* list/dashboard implementation;
* fill-in workflow;
* batch integration;
* Flask backup implementation;
* document-pipeline fixes;
* tests;
* repeated correction loops.

Luna is the sole normal product-code writer.

## Cheap Independent Reviewer — GLM-5.3-Flash

After substantial implementation:

* inspect actual diff;
* review contracts;
* review new state model;
* inspect backup failure behavior;
* check CV regression evidence;
* identify scope drift;
* check tests claimed vs actually executed.

Reviewer remains read-only.

## Escalation — Qwen3.8 Max

Use only if:

* CV root cause remains unresolved after a normal debugging cycle;
* active authoritative sources conflict;
* backup architecture introduces a significant compatibility/security question;
* two Luna correction cycles fail;
* final T2 audit reveals an architectural defect.

Do not use Qwen Max for routine implementation.

---

# 14. Definition of Done

This task is complete only when all of the following are true:

* [ ] CV Contact document replacement and PDF generation are demonstrated working.
* [ ] CV Rinse Pour using the PW/PRW template is demonstrated working.
* [ ] CV Rinse Membrane is regression-tested.
* [ ] New List Dashboard is implemented and visually accepted.
* [ ] Folder/Building context correctly scopes the List.
* [ ] Worksheet selection uses explicit accessible ON/OFF controls.
* [ ] Details can be expanded without changing selection.
* [ ] Selected-work queue shows only selected worksheets.
* [ ] Individual Fill-In works without mutating System DB.
* [ ] Batch-safe Fill-In works only for explicitly safe fields.
* [ ] Single preview/save/print works.
* [ ] Multi-worksheet render/preview/save/print works.
* [ ] Existing controlled document routes remain shared between single and batch paths.
* [ ] Local DOCX/PDF/audit persistence remains working.
* [ ] Configurable project-share backup works.
* [ ] Share-drive outage does not destroy a successful local generation.
* [ ] Failed/pending backups are visible and retryable.
* [ ] Backup integrity is verified deterministically.
* [ ] Existing audit trail records relevant new actions.
* [ ] Representative workflows and CV routes pass regression.
* [ ] Generated representative DOCX/PDF artifacts were actually inspected.
* [ ] Build and relevant validation gates pass.
* [ ] No secrets, production test dumps, generated debug artifacts, or unrelated refactors are included.
* [ ] Independent review has no blocking finding.
* [ ] Final browser visual/interaction review passes.

# Final State

```text
PASS
```

may be declared only after implementation, document artifact verification, regression testing, and independent audit are complete.
