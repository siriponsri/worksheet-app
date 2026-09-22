/* =========================================================================
   Every placeholder in every controlled template has somebody to fill it
   -------------------------------------------------------------------------
   `server/pdf_server.py` substitutes only the keys the browser actually sends
   it. A key that is never sent is not blanked — the loop never visits it — so
   the literal token survives into the DOCX and onto printed paper.

   That failure is invisible from the code: a template-only check can assert
   that the TEMPLATE contains `<gradeControl>`, but nothing proves the PAYLOAD
   can fill it. It printed `<gradeControl>` on every Cleaning
   Validation Contact worksheet until v7.2, and `<floor>` on every EM Air one,
   and both were found by reading a printed page rather than by any gate.

   This reads the real templates and calls the real `documentPayload()`, so it
   cannot drift from either. A standalone validation script would have to
   restate how payload keys are derived, which is the same class of duplication
   that let the bug through.
   ========================================================================= */

import { existsSync, readFileSync } from 'node:fs';
import { inflateRawSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { documentPayload } from './documentPayload';

const templatesDir = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'templates');

/** Reads one entry out of a zip container. A .docx is a zip, and Word writes
 *  `word/document.xml` deflated; no dependency is needed for a single entry. */
function readZipEntry(zipPath: string, entryName: string): string {
  const buffer = readFileSync(zipPath);

  /* End of central directory, scanned from the back: the comment field is
     variable length, so the signature is the only reliable anchor. */
  let eocd = -1;
  for (let at = buffer.length - 22; at >= 0; at -= 1) {
    if (buffer.readUInt32LE(at) === 0x06054b50) { eocd = at; break; }
  }
  if (eocd < 0) throw new Error(`${zipPath} is not a zip container`);

  const entries = buffer.readUInt16LE(eocd + 10);
  let at = buffer.readUInt32LE(eocd + 16);

  for (let index = 0; index < entries; index += 1) {
    if (buffer.readUInt32LE(at) !== 0x02014b50) throw new Error('central directory is malformed');
    const method = buffer.readUInt16LE(at + 10);
    const compressedSize = buffer.readUInt32LE(at + 20);
    const nameLength = buffer.readUInt16LE(at + 28);
    const extraLength = buffer.readUInt16LE(at + 30);
    const commentLength = buffer.readUInt16LE(at + 32);
    const localOffset = buffer.readUInt32LE(at + 42);
    const name = buffer.subarray(at + 46, at + 46 + nameLength).toString('latin1');

    if (name === entryName) {
      /* The local header repeats the name and extra fields with its own
         lengths, so the data offset must be computed from the local copy. */
      const localNameLength = buffer.readUInt16LE(localOffset + 26);
      const localExtraLength = buffer.readUInt16LE(localOffset + 28);
      const start = localOffset + 30 + localNameLength + localExtraLength;
      const data = buffer.subarray(start, start + compressedSize);
      return (method === 0 ? data : inflateRawSync(data)).toString('utf8');
    }
    at += 46 + nameLength + extraLength + commentLength;
  }
  throw new Error(`${entryName} is not in ${zipPath}`);
}

/**
 * Every `<token>` in a template.
 *
 * Word splits a typed token across runs as it pleases — `gradeControl` is
 * stored as `['<','g','rade','C','ontrol','>']` — so the tags are stripped
 * first and the remaining text is matched as a whole. That is also what
 * `_apply_replacements()` in `pdf_server.py` does, and why it works at all.
 * The tokens survive tag-stripping XML-escaped, hence `&lt;` / `&gt;`.
 */
function templateTokens(templateName: string): Set<string> {
  const xml = readZipEntry(join(templatesDir, templateName), 'word/document.xml');
  const flattened = xml.replace(/<[^>]*>/g, '');
  const found: string[] = flattened.match(/&lt;[A-Za-z][A-Za-z0-9_ ]*?&gt;/g) || [];
  return new Set(found.map((token: string) => token.slice(4, -4).replace(/\s+/g, ' ').trim()));
}

/* The seven route keys and the five templates they resolve to, mirroring
   PDF_WORKFLOW_REGISTRY in server/pdf_server.py. */
const ROUTES: { route: string; template: string; method?: string }[] = [
  { route: 'pw-prw', template: 'pw-prw-template.docx' },
  { route: 'wfi-pus', template: 'wfi-pus-template.docx' },
  { route: 'em-air', template: 'em-template.docx' },
  { route: 'compressed-air', template: 'ca-template.docx' },
  { route: 'cleaning-validation-contact', template: 'cv-contact-template.docx' },
  { route: 'cleaning-validation-rinse-pour', template: 'pw-prw-template.docx', method: 'pour-plate' },
  { route: 'cleaning-validation-rinse-membrane', template: 'wfi-pus-template.docx', method: 'membrane-filtration' }
];

const controlledTemplatesAvailable = [...new Set(ROUTES.map(({ template }) => template))]
  .every((template) => existsSync(join(templatesDir, template)));

const templateSuite = controlledTemplatesAvailable ? describe : describe.skip;

templateSuite('controlled template placeholders', () => {
  /* An empty record on purpose: a key present with an empty value is
     substituted with nothing, which is correct. A key that is ABSENT leaves
     the token on the page. Passing no data is therefore the strictest case. */
  it.each(ROUTES)('$route fills every token in $template', ({ route, template, method }) => {
    const tokens = templateTokens(template);
    expect(tokens.size).toBeGreaterThan(0);

    const payload = documentPayload(route, {}, [], 'WS-26-0001', method);
    const unfilled = [...tokens].filter((token: string) => !Object.prototype.hasOwnProperty.call(payload, token)).sort();

    expect(unfilled, `${template} has tokens no payload key fills, so they print as literal text`).toEqual([]);
  });

  it('knows the tokens that regressed before, so they cannot go missing again', () => {
    expect(templateTokens('cv-contact-template.docx')).toContain('gradeControl');
    expect(templateTokens('em-template.docx')).toContain('floor');
  });
});
