# ANF3 Laboratory Records

ANF3 is a read-only React/Vite viewer for Water, Air, Compressed Air, and
Cleaning Validation records. Google Sheets and Apps Script own source records
and worksheet numbering. The local Flask service creates controlled documents
from the five approved DOCX templates.

## Start

1. Configure `ANF3_PROJECT_SHARE` to the controlled worksheet Share. It must
   contain `words`, `pdfs`, `manifests`, `history`, `.locks`, and the central
   `activity-log.jsonl` as the document service creates them.
2. From the release Share, double-click `START-ANF3.bat`. The release is
   refreshed into `%LOCALAPPDATA%\ANF3-Laboratory-Records`.
3. The launcher reuses a healthy ANF3 service, removes stale port state, starts
   Flask on the first available loopback port, waits for `/api/status`, and
   opens that actual port in the browser.

For development, run `pnpm install`, `pnpm dev`, and `START-SERVER.bat` in
separate terminals as needed. `START-SERVER.bat` requires
`ANF3_PROJECT_SHARE`; it never falls back to the checkout or Local AppData for
controlled storage.

## Architecture

```text
Google Sheets -> User Apps Script -> RPP2 System Apps Script -> React read API
                                                        -> IndexedDB cache
React print payload -> Flask -> approved DOCX template -> Share DOCX and PDF
```

The browser never writes records or receives a sync token. Local AppData is
disposable application/runtime/cache state. Controlled documents, manifests,
history, locks, and logs are Share-owned.

## Workflows

| Workflow | PDF route | Template | Capacity | Worksheet prefix |
| --- | --- | --- | ---: | --- |
| PW/PRW | `pw-prw` | `templates/pw-prw-template.docx` | 30 | `WT-` |
| WFI/PUS | `wfi-pus` | `templates/wfi-pus-template.docx` | 30 | `WP-` |
| EM Air | `em-air` | `templates/em-template.docx` | 50 | `AT-` |
| Compressed Air | `compressed-air` | `templates/ca-template.docx` | 10 | `AC-` |
| CV Contact | `cleaning-validation-contact` | `templates/cv-contact-template.docx` | 10 | `CV-` |
| CV Rinse Pour | `cleaning-validation-rinse-pour` | PW/PRW template family | 30 | `CVR-` |
| CV Rinse Membrane | `cleaning-validation-rinse-membrane` | WFI/PUS template family | 30 | `CVR-` |

Controlled filenames are `<worksheetNo>.docx` and `<worksheetNo>.pdf`.
Worksheet format is `<PREFIX>-YY-<B10|B12|B16|OT>-####`.

See these active contracts for details:

- `docs/CABINET_WORKFLOW_MATRIX.md` - building and binder routing.
- `docs/CV_TEMPLATE_ROUTING_CONTRACT.md` - CV method/template routing.
- `docs/APPS_SCRIPT_6_FILE_CONTRACT.md` - six Apps Script project bundles.
- `docs/GOAL.md` - release acceptance criteria.
- `OWNER_DEPLOYMENT.md` - owner-only Apps Script update checklist.

## Verification

```powershell
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

Use `validation/run_local_validation.mjs` for the complete local-only gate.
Live Apps Script deployment and production Sheets checks remain owner actions.

## Safety

Do not fabricate laboratory values, deploy Apps Script, mutate production
Sheets, alter controlled template contents, or use Local AppData as document
storage. Air fixes must be reproduced against the exact failing request and
regressed against Compressed Air before they are accepted.
