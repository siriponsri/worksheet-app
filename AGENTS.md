# ANF3 Repository Guidelines

ANF3 is a read-only React/Vite laboratory-record viewer over Google Sheets and
Apps Script, with a local Flask service that fills controlled DOCX templates
and converts them to PDF.

## Active Architecture

```text
Google Sheets -> User Apps Script -> RPP2 System Apps Script
                                      -> public read /exec
React app (apps/web) -> IndexedDB read cache
                     -> Flask POST route
Flask (server/pdf_server.py) -> templates/*.docx -> Share DOCX/PDF
```

Active code is limited to `apps/web/`, `server/`, `google/app-scripts/`,
`templates/`, and `validation/`, plus the root launch/build configuration.
The Flask service serves `dist/` and the inventory catalogue; it does not
serve retired root HTML or vanilla JavaScript pages.

## Commands

```powershell
pnpm install
pnpm check
pnpm test
pnpm build
python -m pytest server/tests -q

node validation/test_apps_script_security.mjs
node validation/test_cv_contract.mjs
node validation/test_worksheet_numbering.mjs
node validation/validate_non_game_contract.mjs
node validation/validate_wiring.mjs --built
python validation/validate_release.py
git diff --check
```

Run `pnpm check && pnpm test && pnpm build` before the server tests. Run
`validation/run_local_validation.mjs` for the complete local gate. Browser and
live Apps Script checks require an explicitly running local service or owner
deployment and must be reported as not tested when unavailable.

For the local service, run `INSTALL.bat` once and then `START-SERVER.bat`, or
use `START-ANF3.bat` from the release Share. The launcher copies the release
to `%LOCALAPPDATA%\ANF3-Laboratory-Records`, reuses only a healthy ANF3
service, and lets Flask choose an available loopback port. Controlled storage
must be supplied through the server-only `ANF3_PROJECT_SHARE` environment
variable.

## Seven Workflow Contracts

| Workflow | UI/domain | PDF route | Template | Capacity | Worksheet prefix |
| --- | --- | --- | --- | ---: | --- |
| PW/PRW | `pw-prw` / water | `pw-prw` | `pw-prw-template.docx` | 30 | `WT-` |
| WFI/PUS | `wfi-pus` / water | `wfi-pus` | `wfi-pus-template.docx` | 30 | `WP-` |
| EM Air | `em-air` / air | `em-air` | `em-template.docx` | 50 | `AT-` |
| Compressed Air | `compressed-air` / air | `compressed-air` | `ca-template.docx` | 10 | `AC-` |
| CV Contact | `cv` / cv | `cleaning-validation-contact` | `cv-contact-template.docx` | 10 | `CV-` |
| CV Rinse Pour | `cv` / cv | `cleaning-validation-rinse-pour` | `pw-prw-template.docx` | 30 | `CVR-` |
| CV Rinse Membrane | `cv` / cv | `cleaning-validation-rinse-membrane` | `wfi-pus-template.docx` | 30 | `CVR-` |

Worksheet identity is `<PREFIX>-YY-<B10|B12|B16|OT>-####`. The Worksheet No
is the controlled DOCX/PDF filename and manifest identity. A content hash is
only an internal cache/conflict identity.

## Non-Negotiable Contracts

- Building routing is only `B10`, `B12`, `B16`, and `OT`. Building 11, 19,
  blank, or unknown values map to `OT`; never create a B11 or B19 shard.
- CV contact storage is plural: `records_cv_contact_B10/B12/B16/OT`.
  CV rinse storage is singular: `record_cv_rinse_B10/B12/B16/OT`.
- CV `Test-Method` is authoritative. Rinse Pour Plate uses the PW/PRW
  template family; Rinse Membrane Filtration uses the WFI/PUS family.
- WFI/PUS uses sample `result`; PW/PRW uses `result1`, `result2`, and
  `resultAvg`; CV Pour maps source `Result` to `resultAvg`; CV Rinse Membrane
  uses `result`. Never fabricate replicates, tags, lots, equipment, dates,
  approvals, or results.
- Compressed Air has record-level `tempRoom01` from `record.temp` and sample
  `temp01` through `temp10`; do not invent `tempRoom02` through `tempRoom10`.
- DOCX templates are authoritative. Inspect `word/document.xml` before
  changing a placeholder mapping. Preserve known aliases and exact whitespace.
- Each multipage `pages[n]` dictionary is self-contained.
- The browser reads records and posts print payloads to Flask. It never writes
  Sheets, creates worksheet numbers, syncs records, or receives a mutation
  token. `ANF3_SYNC_TOKEN` belongs only in Apps Script properties or the
  optional server log-forward file.
- Controlled files and the activity log live only under the configured Share:
  `words/`, `pdfs/`, `manifests/`, `history/`, `.locks/`, and
  `activity-log.jsonl`. Local AppData is disposable runtime/cache only.
- Individual controlled files are `<worksheetNo>.docx` and
  `<worksheetNo>.pdf`. A changed payload under an existing Worksheet No must
  return `409 WORKSHEET_CONTENT_CONFLICT`, never silently overwrite it.
- Air changes must be reproduced from the exact request first and compared
  with Compressed Air. Trace UI filters, `api.ts`, the deployed endpoint,
  shard selection, response items, and record scoping before changing code.

## Apps Script Safety

`google/app-scripts/` contains exactly six deployable bundles: three User
scripts and three System scripts. Do not deploy them, mutate production Sheets,
change permissions, or alter live counters in a coding task. Any required
deployment, resync, or production verification is `OWNER_ACTION_REQUIRED`.
The six-file contract is documented in `docs/APPS_SCRIPT_6_FILE_CONTRACT.md`.

## Evidence-First Debugging

Reproduce the reported behavior, record the exact request and response, trace
the active execution path, identify the root cause from repository evidence,
make the smallest fix, rerun the original reproduction, then run adjacent
regression tests. Inspect generated DOCX XML and PDF output physically when a
document path changes. Do not claim a command passed unless it was executed.

## Single-Session Workflow

The default workflow is one implementation owner:

```text
User -> Luna Max -> inspect -> reproduce -> implement -> test -> self-review
      -> fix regressions -> commit -> report
```

Do not create orchestration handoffs for ordinary work. Keep changes surgical
and out of unrelated Quant Motion or visual redesign work.

## Skills

- `anf3-debug`: evidence-first bug reproduction and root-cause debugging.
- `anf3-document-pipeline`: RPP2 mapping, templates, DOCX/PDF generation.
- `karpathy-guidelines`: small, evidence-supported implementation changes.

## Editing Rules

Use the active source and tests as repository truth. Preserve unrelated user
changes. Use `apply_patch` for manual edits. Do not commit generated DOCX/PDF,
runtime logs, secrets, local paths, or temporary files. Do not edit frozen or
retired code to preserve compatibility; remove it only after proving the
active release does not use it.
