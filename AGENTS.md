# ANF3 Repository Guidelines

ANF3 is a read-only React/Vite/TypeScript laboratory-record viewer over a Google Sheets / Apps Script System DB, with a local Flask service that fills controlled DOCX templates and converts to PDF.

## Commands

```powershell
pnpm install
pnpm dev          # Vite 127.0.0.1:5173; /api proxied to Flask :8000
pnpm check        # tsc -b (typecheck only)
pnpm test         # vitest run
pnpm build        # tsc -b && vite build → ./dist

# Flask server (separate terminal)
INSTALL.bat                    # one-time Python venv
INSTALL-MSOFFICE-SUPPORT.bat   # one-time Word→PDF converter
START-SERVER.bat               # Flask on 127.0.0.1:8000

# Single test
pnpm vitest run path/to/file.test.ts
pnpm vitest run path/to/file.test.ts -t "test name"
python -m pytest server/tests -k name

# Validation gates (each is a standalone script)
node validation/test_cv_contract.mjs
node validation/test_worksheet_numbering.mjs
node validation/validate_wiring.mjs --built
python validation/validate_release.py
```

Order: `pnpm check && pnpm test && pnpm build`, then `python -m pytest server/tests`, then affected validation gates.

## Architecture

```
Google Sheets → User Apps Script → RPP2 System Apps Script
                                         ↓ public read /exec
React app (apps/web/) → IndexedDB cache
         ↓ POST route + payload
Flask (server/pdf_server.py) → DOCX template → filled .docx → .pdf
```

- `apps/web/src/` — active React app (hash router, `App.tsx` is ~2000 lines)
- `apps/web/src/documentPayload.ts` — canonical placeholder mapper + page splitter
- `apps/web/src/recordPolicy.ts` — CV method normalization, PDF route selection
- `apps/web/src/api.ts` — System DB read calls; uses opaque cursors
- `server/pdf_server.py` — template registry (`PDF_WORKFLOW_REGISTRY`), route validation, DOCX fill, PDF conversion
- `templates/` — 5 authoritative DOCX templates; inspect XML before changing any mapping
- `google/app-scripts/` — 6 deployable bundles (3 User + 3 System); see `docs/APPS_SCRIPT_6_FILE_CONTRACT.md`
- `js/`, `css/`, `pw-prw/`, `wfi-pus/`, `em-air/`, `compressed-air/`, `cv/`, root `*.html` — frozen legacy fallback; do not edit
- `validation/` — contract, release, and fixture checks
- `_archived/` — legacy reference only

## Vite envDir gotcha

`vite.config.ts` has `root: 'apps/web'` but `.env.production` is at the repo root, so `envDir: '../../'` is required. Without it, `VITE_*_READ_URL` vars are silently dropped and every domain reports "not configured". `validate_wiring.mjs --built` catches this.

## Seven workflows

| Workflow | UI ID | PDF route key | Template | Capacity | Worksheet prefix |
|---|---|---|---|---:|---|
| PW/PRW | `pw-prw` | `pw-prw` | `pw-prw-template.docx` | 30 | `WT-` |
| WFI/PUS | `wfi-pus` | `wfi-pus` | `wfi-pus-template.docx` | 30 | `WP-` |
| EM Air | `em-air` | `em-air` | `em-template.docx` | 50 | `AT-` |
| Compressed Air | `compressed-air` | `compressed-air` | `ca-template.docx` | 10 | `AC-` |
| CV Contact | `cv` | `cleaning-validation-contact` | `cv-contact-template.docx` | 10 | `CV-` |
| CV Rinse Pour | `cv` | `cleaning-validation-rinse-pour` | `pw-prw-template.docx` | 30 | `CVR-` |
| CV Rinse Membrane | `cv` | `cleaning-validation-rinse-membrane` | `wfi-pus-template.docx` | 30 | `CVR-` |

Worksheet format: `<PREFIX>-YY-<B10|B12|B16|OT>-####`.

## Contracts an agent will get wrong

### Building routing
Only `B10`, `B12`, `B16`, `OT`. Building 11/19/blank/unknown → `OT`. Never invent `B11` or `B19` shards.

### CV storage naming
Contact shards are **plural**: `records_cv_contact_B10/B12/B16/OT`.
Rinse shards are **singular**: `record_cv_rinse_B10/B12/B16/OT`. Do not "fix" the inconsistency.

### CV method routing
`Test-Method` is authoritative, not the sampling-method label. `Rinse-PW` + membrane filtration → WFI/PUS membrane route, not PW/PRW.

### Sample result fields
- **WFI/PUS**: `result` (single field), mapped to `result01`–`result30`. Not `resultAvg`.
- **PW/PRW**: `result1`, `result2`, `resultAvg`, mapped to `result1NN`, `result2NN`, `resultAvgNN`.
- **CV Pour Plate**: source `Result` → `resultAvgNN`; `result1NN` and `result2NN` stay blank. Do not fabricate replicates.
- **CV Rinse Membrane**: `resultNN`. Not `resultAvgNN`. Do not fabricate replicates.
- **CV Rinse `tagNo`**: blank unless a real source supplies it. Never manufacture from row/location/worksheet number.

### Placeholder aliases (inspect DOCX XML before changing)
- `lotPMembrane` → template `lotMembrane`
- `leftEM` / `rightEM` → template `leftEm` / `rightEm`
- Contact placeholder may have whitespace: `<samplingTime >`

### Compressed Air temperature
Template has only record-level `<tempRoom01>` (from `record.temp`). Per-sample: `temp01`–`temp10`. Do not invent `tempRoom02`–`tempRoom10`.

### Multipage rendering
Each `pages[n]` dictionary must be **self-contained** (header fields + that page's samples). Flask does not merge top-level `data` into pages.

### Output identity
Filenames are `<worksheetNo>.docx` / `<worksheetNo>.pdf`. Content hash is internal cache only. Content change under existing worksheet → `409 WORKSHEET_CONTENT_CONFLICT`; never silently overwrite.

## Non-negotiable rules

1. **Browser never writes records.** It reads System DB and posts to local Flask only.
2. **No mutation token in browser config.** `ANF3_SYNC_TOKEN` lives only in Apps Script properties and optionally `server/log-forward.json`.
3. **Templates are authoritative layout artifacts.** Inspect `word/document.xml` before changing any mapping. Never recreate a form from scratch.
4. **Never fabricate** results, control values, media lots, equipment IDs, dates, tags, replicates, or approvals. Missing data → blank.
5. **A new PDF route requires three changes**: `recordPolicy.ts`, `PDF_WORKFLOW_REGISTRY` in `pdf_server.py`, and `docs/CV_TEMPLATE_ROUTING_CONTRACT.md`. Validation gates fail if they disagree.
6. **Do not edit** `server/`, `google/app-scripts/`, `templates/`, or frozen legacy pages without explicit request.
7. **Timezone**: `Asia/Bangkok` where the system relies on it.

## Token discipline (CSS)

No inline hex, `oklch()`, `rgb()`, or bare `font-family` outside `apps/web/src/tokens.css`. Add a named token. Run `node validation/contrast.mjs` after palette edits.

## OpenCode Agent Protocol

ANF3 uses a **single-session orchestrated multi-agent workflow by default**.

The purpose of multiple agents is separation of responsibility and cost-efficient model routing. It does **not** require multiple terminals, multiple Git worktrees, or concurrent coding sessions.

### Default topology

```text
User
  ↓
Astra — primary orchestrator / planner / final authority
  ├── Explorer — repository evidence gathering
  ├── Luna — implementation, tests, and fixes
  ├── Reviewer — independent hostile review
  └── Astra-Max — expensive deep reasoning and high-risk final gate
```

Only Luna owns normal product-code writes.

Astra, Explorer, Reviewer, and Astra-Max MUST remain read-only for product code unless the user explicitly transfers write ownership.

### Model routing

Use the cheapest model that can safely perform the task.

| Agent       | Default role                                                       | Model tier          |
| ----------- | ------------------------------------------------------------------ | ------------------- |
| `astra`     | orchestration, task classification, planning, acceptance           | Qwen3.8 Flash       |
| `explorer`  | grep, file discovery, execution-path tracing, evidence collection  | DeepSeek V4.1 Flash |
| `luna`      | implementation, debugging, tests, correction loops                 | GPT-5.6 Luna        |
| `reviewer`  | independent audit, regression review, acceptance review            | GLM-5.3 Flash       |
| `astra-max` | difficult root cause, architecture, high-risk planning/final audit | Qwen3.8 Max         |

Model names are configuration, not repository contracts. If a configured model becomes unavailable, substitute a model of comparable role/cost without changing the responsibility boundaries in this file.

### Cost discipline

Do not use an expensive reasoning model for routine repository exploration, repetitive test execution, formatting, mechanical edits, or ordinary fix loops.

Prefer:

```text
cheap exploration
→ concentrated reasoning
→ economical implementation loop
→ cheap independent audit
→ expensive final reasoning only when justified
```

Astra-Max SHOULD normally receive an evidence packet rather than independently rescanning the repository from scratch.

### Task classification

Astra MUST classify the task before implementation.

#### T0 — Trivial

Examples:

* typo;
* isolated copy change;
* obvious CSS defect;
* mechanical change with an existing exact test.

Default flow:

```text
Astra
→ Luna
→ focused verification
→ done
```

Reviewer and Astra-Max are unnecessary unless the change exposes unexpected behavior.

#### T1 — Standard

Examples:

* ordinary bug;
* localized feature;
* one-layer behavior change;
* test failure with a reproducible cause.

Default flow:

```text
Explorer when useful
→ Astra plan
→ Luna implement + test
→ Reviewer audit
→ Astra close
```

#### T2 — High Risk / Cross-Layer

Escalate when any of the following applies:

* more than two runtime layers are affected;
* Apps Script and frontend/backend behavior interact;
* data contract or schema changes;
* worksheet numbering or identity changes;
* DOCX placeholder/template mapping changes;
* CV route/method/template behavior changes;
* security, credentials, permissions, or sensitive configuration;
* migration or architectural refactor;
* authoritative repository sources conflict;
* the same defect survives two implementation cycles;
* root cause remains uncertain after evidence gathering;
* release-critical regression.

Default flow:

```text
Explorer evidence
→ Astra-Max deep plan
→ Luna implement + verify
→ Reviewer hostile audit
→ Luna targeted correction if required
→ Astra-Max final gate
→ Astra close
```

Do not escalate merely because a task is large in line count. Escalate because reasoning risk or consequence is high.

### Astra — primary orchestrator

Astra owns:

* interpreting the user goal;
* classifying T0/T1/T2;
* deciding which subagents are necessary;
* inspecting repository state before delegation;
* defining acceptance criteria;
* maintaining `.agent-bus/CURRENT_TASK.md` when a persistent task packet is useful;
* evaluating Reviewer findings;
* escalating to Astra-Max when required;
* declaring final completion.

Astra MUST NOT:

* modify normal product code;
* perform repetitive implementation work that belongs to Luna;
* invoke Astra-Max for routine work;
* declare success solely from Luna's report;
* treat an unexecuted test as passed;
* mutate production or external systems without explicit user approval.

### Explorer — evidence gatherer

Explorer is read-only.

Use Explorer for:

* locating relevant files;
* grep/search;
* tracing imports and call paths;
* identifying tests and fixtures;
* collecting exact repository evidence;
* comparing active implementations;
* identifying likely blast radius.

Explorer SHOULD return concise evidence with file paths and relevant facts.

Explorer MUST NOT:

* edit files;
* decide business rules;
* design speculative architecture;
* repeatedly reread broad portions of the repository after sufficient evidence has been collected.

### Luna — sole implementation owner

Luna owns:

* product-code edits;
* implementation-side test changes;
* focused debugging;
* running the original reproduction;
* running adjacent regression checks;
* fixing defects introduced by its changes;
* reviewing its final diff.

Before editing, Luna MUST inspect the relevant active implementation and the current task requirements.

Luna MUST make the smallest evidence-supported change that satisfies the goal.

Luna MUST NOT:

* broaden scope for cleanup;
* reinterpret legacy contracts for consistency;
* fabricate missing laboratory/business data;
* silently resolve conflicting authoritative sources;
* modify unrelated UI or architecture;
* deploy or mutate production/external systems without explicit approval.

For substantial tasks, Luna SHOULD record the implementation result in `.agent-bus/LUNA_REPORT.md`.

### Reviewer — independent hostile audit

Reviewer is read-only for product code.

Reviewer evaluates the actual diff and verification evidence rather than Luna's narrative alone.

Review for:

* correctness against the user goal;
* acceptance-criteria compliance;
* regressions;
* contract drift;
* unresolved placeholders or mapping errors where applicable;
* suspicious unrelated changes;
* generated/debug artifacts;
* secret or production-data leakage;
* claims of tests that were not actually run.

Findings MUST be concrete and falsifiable.

Use severity:

```text
blocking
major
minor
```

Preference-only comments MUST NOT block completion unless they were part of the original acceptance criteria.

### Astra-Max — expensive reasoning gate

Astra-Max is read-only for product code.

Use Astra-Max only when:

* the task is classified T2;
* evidence remains contradictory or difficult to reconcile;
* two normal fix cycles fail;
* Reviewer finds a potentially architectural or high-consequence defect;
* final acceptance involves a high-risk contract.

Astra-Max SHOULD receive:

```text
user goal
+ focused repository evidence
+ execution path
+ current diff when applicable
+ failing reproduction/test
+ acceptance criteria
+ Reviewer findings when applicable
```

Do not ask Astra-Max to perform routine grep/search work that Explorer can perform.

### Correction loop

When Reviewer finds a real defect:

```text
Reviewer finding
→ Astra validates the finding
→ Luna performs a targeted correction
→ original failing verification is rerun
→ adjacent regression is rerun
→ Reviewer rechecks only when materially useful
```

Escalate to Astra-Max after two unsuccessful normal correction cycles or immediately for a T2 issue.

Do not create an endless subjective review loop.

### Agent Bus

`.agent-bus/` is persistent coordination state, not application runtime state.

Recommended files:

```text
.agent-bus/
├── CURRENT_TASK.md
├── LUNA_REPORT.md
├── ASTRA_AUDIT.md
└── STATUS.json
```

In the default single-session OpenCode workflow, `LOCK.json` is optional because only Luna owns product-code writes and agents execute sequentially.

Use `LOCK.json` when:

* more than one OpenCode session is running;
* multiple terminals are used;
* separate worktrees are used;
* another write-capable coding process may edit the same repository concurrently.

Do not commit runtime Agent Bus files unless the user explicitly wants them preserved.

### STATUS.json

For substantial T1/T2 tasks, recommended fields are:

```json
{
  "task_id": "ANF3-YYYYMMDD-001",
  "task_class": "T1",
  "state": "IMPLEMENTING",
  "write_owner": "luna",
  "iteration": 1,
  "max_escalated": false
}
```

Allowed lifecycle:

```text
PLANNING
READY_FOR_IMPLEMENTATION
IMPLEMENTING
READY_FOR_REVIEW
CHANGES_REQUIRED
READY_FOR_FIX
FINAL_REVIEW
PASS
BLOCKED
```

Do not create Agent Bus state for every trivial T0 edit.

### Completion authority

`LUNA_REPORT.md` saying implementation is complete does not by itself mean the task is complete.

For T1, completion normally requires:

```text
implementation verified
+ Reviewer has no blocking finding
+ Astra acceptance
```

For T2, completion normally requires:

```text
implementation verified
+ Reviewer has no blocking finding
+ Astra-Max final review
+ Astra acceptance
```

### Multi-terminal mode

Multiple terminals are **not required**.

Default:

```text
one repository
+ one OpenCode session
+ one Astra primary agent
+ specialized subagents
```

Use multiple terminals or worktrees only when the user explicitly wants parallel work or stronger process isolation.

When multi-terminal mode is active:

* only one writer may own overlapping product files;
* use `.agent-bus/LOCK.json`;
* all sessions must inspect `git status` before acting;
* separate worktrees are preferred for genuinely parallel non-overlapping implementation;
* never run two independent implementation agents against the same files.

### Stop conditions

Repository stop conditions elsewhere in this file override agent autonomy.

No model tier, including Astra-Max, grants permission to mutate production systems, deploy Apps Script, alter live Google Sheets, fabricate laboratory data, or break documented compatibility contracts.


## Stop conditions — ask the user before:

1. Mutating/deleting production data or Google Sheets
2. Deploying or reconfiguring a live Apps Script deployment
3. Resolving a genuine conflict between two authoritative active sources
4. A fix that would fabricate missing laboratory/business data
5. Breaking a documented compatibility contract

## Skills

- `$anf3-document-pipeline` — RPP2 mapping, template routing, DOCX/PDF generation
- `$anf3-debug` — evidence-first debugging (reproduce → trace → evidence → root cause → fix → re-verify)
- `$karpathy-guidelines` — surgical changes during edits/refactors
