# ANF3 Release Completion Goal

## Objective

Complete the share-drive release audit and fix only defects proven by controlled verification. Completion requires the public-source gates, real controlled assets, and a clean Windows launch test, or an evidence-backed external blocker.

Do not redesign the frontend, change laboratory data contracts, mutate production Sheets, deploy Apps Script, edit official templates, or commit controlled/owner-only assets.

## Baseline to preserve

- Preserve worksheet identity and `<worksheetNo>.docx` / `<worksheetNo>.pdf` filenames.
- Preserve B10/B12/B16/OT routing, B11/B19 -> OT behavior, historical numbers, CV shard names, `Test-Method` routing, legacy aliases, and template-family routes.
- Preserve `GENERATE`, `NO_CHANGE`, and controlled `CONFLICT`; never silently truncate samples or overwrite changed artifacts.
- Every independently rendered page contains its own record/header fields plus its page samples.
- Missing values remain blank; never fabricate laboratory or approval data.
- Keep templates, generated outputs, secrets, and production exports outside Git.

## Work required

1. Assemble an external controlled release directory containing the five authoritative DOCX templates, owner documents/catalog, built `dist`, config, server, and supported Word/LibreOffice converter. Record its exact path and version.
2. Run the release and non-game validators with `--controlled-dir`; fix implementation-caused failures without weakening validation:

   ```powershell
   python validation/validate_release.py --controlled-dir <release-directory>
   node validation/validate_non_game_contract.mjs --controlled-dir <release-directory>
   ```

3. Using representative non-production fixtures, generate and inspect real DOCX/PDF for PW/PRW, WFI/PUS, EM, Compressed Air, CV Contact, CV Rinse Pour Plate, and CV Rinse Membrane Filtration. Verify authoritative routing, exact mappings and aliases, capacity handling, page self-containment, unresolved-placeholder rejection, layout, filenames, `NO_CHANGE`, and `CONFLICT`.
4. On a clean Windows machine without Node.js or pnpm, launch `START-ANF3.bat` from UNC/share. Test local copy, status wait, healthy reuse, safe version refresh, converter and browser flow, plus actionable failures for missing/broken runtime, `dist`, template, converter, port, offline endpoint, and concurrent launch.
5. With owner-approved non-production Sheets and `/exec` URLs, verify filters, building aliases, summaries, date/result formatting, OT/CV routing, capacities, duplicate protection, legacy recovery, and deployed revision parity. Stop before production mutation or live redeploy.

## Verification and handoff

After each fix run the smallest relevant check, then the applicable public suite, the controlled commands above, and `git diff --check`. Remove generated artifacts and diagnostics. Record command results and limitations in the task report, not in the product runtime.

## Definition of done

Report release readiness only when controlled validation, all seven real document routes, cache/conflict/multipage behavior, clean-PC UNC launch, and approved non-production Apps Script checks pass, with no unrelated refactor, controlled asset, secret, generated output, or stale documentation reference in the final diff.

If an item cannot run because an external dependency is unavailable, report `NEEDS_EVIDENCE` or `BLOCKED` with the exact missing asset/system and command. Public-source tests alone are insufficient.
