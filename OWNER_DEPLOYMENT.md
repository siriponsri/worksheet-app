# Owner Deployment Checklist

The coding agent does not deploy Apps Script or modify production Sheets. The
owner must update the six projects below only after reviewing the diff and
running the local validation gates.

| File | Apps Script project | Deployment role |
| --- | --- | --- |
| `google/app-scripts/air-test.gs` | Air User | Bound source-sheet sync |
| `google/app-scripts/RPP2-air-record.gs` | Air System DB | Read `/exec` web app and controlled system store |
| `google/app-scripts/water-r.gs` | Water User | Bound source-sheet sync |
| `google/app-scripts/RPP2-water-record.gs` | Water System DB | Read `/exec` web app and controlled system store |
| `google/app-scripts/Testing.gs` | Cleaning Validation User | Bound source-sheet sync |
| `google/app-scripts/RPP2-cv-record.gs` | Cleaning Validation System DB | Read `/exec` web app and controlled system store |

Deploy the three System files to their matching System DB projects. Update the
three User files in their bound source-sheet projects. Preserve the existing
deployment URLs and Script Properties, including the sync token; never put a
token in `config.json`, `.env.production`, or browser code.

After owner deployment:

1. Confirm each System `/exec` endpoint responds to its health/read contract.
2. Confirm the User project points to the matching System URL and Script
   Properties remain configured.
3. Run read-only Air, Compressed Air, Water, and CV searches for B10, B12,
   B16, and Other as applicable.
4. Confirm the local server status shows the configured Share as available.
5. Generate one approved non-production document and verify the Share contains
   `<worksheetNo>.docx`, `<worksheetNo>.pdf`, and its manifest.

Any production resync, permission change, counter change, or live document
mutation is an owner-controlled action and is outside this repository task.
