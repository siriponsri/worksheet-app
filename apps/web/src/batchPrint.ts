/* =========================================================================
   Printing a batch of worksheets
   -------------------------------------------------------------------------
   The lab prints a run of worksheets at a time, not one. Firing the browser's
   print dialog once per worksheet is unusable past about three, so the
   selected records are generated one at a time on the local server — the same
   `/api/pdfs` route and the same controlled templates as a single print, no
   new server surface — and then stitched into one document in the browser.

   That gives one print dialog, one paper stack in worksheet order, and one
   file if they would rather save it. Merging happens here rather than on the
   server because the pages are already rendered and controlled by then:
   nothing about the document content is decided in the browser.

   Rendering and merging are two steps, not one, because the operator needs to
   SEE the stack before it reaches paper. `renderBatch()` returns each
   worksheet as its own document with its page count; the preview shows them,
   lets the operator drop the ones they did not mean to print, and only then
   does `mergeParts()` build the document that is actually printed. Dropping a
   worksheet in the preview costs nothing — it is already rendered, so no
   second trip to the server is needed to change the selection.
   ========================================================================= */

import { PDFDocument } from 'pdf-lib';
import { getSystemRecord } from './api';
import { getCachedRecord } from './storage';
import type { Workflow } from './appData';
import { normalizeCvTestMethod, pdfRouteForRecord, cvSamplingFamily } from './recordPolicy';
import { documentPages, documentPayload } from './documentPayload';
import type { RecordData } from './storage';
import { mergePrintFill, printFieldLabel, printableFields } from './printFill';

export type BatchItem = { recordKey: string; worksheetNo: string };
export type BatchDrafts = Record<string, Record<string, string>>;

export type BatchProgress = {
  done: number;
  total: number;
  current: string;
};

/** One rendered worksheet, held on its own so the preview can drop it. */
export type BatchPart = {
  recordKey: string;
  worksheetNo: string;
  bytes: ArrayBuffer;
  pageCount: number;
  pdfId?: string;
  backupStatus?: 'succeeded' | 'pending' | 'disabled' | 'failed';
  backupError?: string;
};

export type BatchConflict = {
  recordKey: string;
  worksheetNo: string;
  requestedPdfId: string;
  existingPdfIds: string[];
  changedFields: string[];
};

export type BatchRender = {
  parts: BatchPart[];
  /** Worksheets that could not be rendered, with the reason. */
  skipped: { worksheetNo: string; reason: string }[];
  conflicts: BatchConflict[];
};

export class BatchConflictError extends Error {
  constructor(public conflict: BatchConflict) {
    super('This worksheet already has a generated document');
  }
}

type BatchReplacement = Pick<BatchConflict, 'requestedPdfId' | 'existingPdfIds'>;

const SAMPLE_KEY_PREFIXES: Record<string, string[]> = {
  'pw-prw': ['samplingPoint', 'tagNo', 'result1', 'result2', 'resultAvg'],
  'wfi-pus': ['samplingPoint', 'tagNo', 'result'],
  'em-air': ['roomNo', 'grade', 'tempRoom', 'rhRoom', 'timeIn', 'timeOut', 'occurResult', 'remark'],
  'compressed-air': ['roomNo', 'grade', 'temp', 'rh', 'occResult', 'remark'],
  'cleaning-validation-contact': ['samplingPoint', 'Grade', 'result'],
  'cleaning-validation-rinse-pour': ['tagNo', 'samplingPoint', 'result1', 'result2', 'resultAvg'],
  'cleaning-validation-rinse-membrane': ['tagNo', 'samplingPoint', 'result']
};

function isSampleKey(route: string, key: string) {
  return (SAMPLE_KEY_PREFIXES[route] || []).some((prefix) => new RegExp(`^${prefix}\\d+$`).test(key));
}

function mergePageDraft(route: string, page: Record<string, string>, draft: Record<string, string>, pageIndex: number) {
  const merged = mergePrintFill(page, draft, route);
  if (pageIndex === 0) return merged;
  /* The current Fill-in drawer keys sample rows from page one. Do not
     accidentally copy those edits into page two; header edits still repeat. */
  Object.keys(page).filter((key) => isSampleKey(route, key)).forEach((key) => { merged[key] = page[key]; });
  return merged;
}

export function buildDocumentRequestPayload(
  route: string,
  record: RecordData,
  samples: RecordData[],
  worksheetNo: string,
  method?: string,
  draft: Record<string, string> = {}
) {
  const payload = mergePrintFill(documentPayload(route, record, samples, worksheetNo, method), draft, route);
  const pages = documentPages(route, record, samples, worksheetNo, method)
    .map((page, pageIndex) => mergePageDraft(route, page, draft, pageIndex));
  return {
    data: payload,
    ...(pages.length > 1 ? { pages } : {})
  };
}

async function pdfForRecord(
  workflow: Workflow,
  recordKey: string,
  worksheetNo: string,
  presetMethod?: string,
  draft: Record<string, string> = {},
  regeneration?: BatchReplacement,
) {
  const cached = await getCachedRecord(workflow.domain, workflow.id, recordKey);
  const value = cached ?? await getSystemRecord(workflow, recordKey);
  const record = value.record;
  const method = presetMethod || (workflow.id === 'cv' ? normalizeCvTestMethod(record.testMethod || record.samplingMethod) : undefined);
  const route = pdfRouteForRecord(workflow, record, method);
  if (!route) {
    throw new Error(cvSamplingFamily(record) === 'rinse'
      ? 'the rinse test method is not set on this record'
      : 'no template is configured for this workflow');
  }
  const document = buildDocumentRequestPayload(
    route,
    record,
    value.samples,
    worksheetNo,
    method,
    draft
  );
  const payload = document.data;
  const requestBody: Record<string, unknown> = {
    workflow: route,
    worksheetNo,
    cvContext: workflow.id === 'cv'
      ? { samplingFamily: cvSamplingFamily(record), testMethod: method }
      : undefined,
    ...document
  };
  if (regeneration) requestBody.regeneration = { mode: 'replace', ...regeneration };
  const response = await fetch('/api/pdfs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody)
  });
  const result = await response.json();
  if (response.status === 409 && result.code === 'WORKSHEET_CONTENT_CONFLICT') {
    const fields = printableFields(payload, route);
    const changedFields: string[] = Array.isArray(result.changedFields)
      ? result.changedFields.map((key: unknown) => printFieldLabel(String(key), fields) as string)
      : [];
    throw new BatchConflictError({
      recordKey,
      worksheetNo,
      requestedPdfId: String(result.requestedPdfId || ''),
      existingPdfIds: Array.isArray(result.existingPdfIds) ? result.existingPdfIds.map(String) : [],
      changedFields: [...new Set<string>(changedFields)]
    });
  }
  if (!response.ok) throw new Error(result.error || 'the server refused it');
  const file = await fetch(`/api/pdfs/${result.pdfId}/download`);
  if (!file.ok) throw new Error('the rendered file could not be read back');
  return {
    bytes: await file.arrayBuffer(),
    route,
    pdfId: String(result.pdfId || ''),
    backupStatus: result.backup?.status,
    backupError: result.backup?.error
  };
}

/**
 * Renders every selected worksheet, in the order given, keeping each as its
 * own document. One failure does not stop the run — the reason is reported per
 * worksheet, so a batch of forty is not lost to one record with a missing
 * method.
 */
export async function renderBatch(
  workflow: Workflow,
  items: BatchItem[],
  presetMethod: string | undefined,
  drafts: BatchDrafts,
  onProgress: (progress: BatchProgress) => void,
  signal?: AbortSignal
): Promise<BatchRender> {
  const parts: BatchPart[] = [];
  const skipped: { worksheetNo: string; reason: string }[] = [];
  const conflicts: BatchConflict[] = [];

  for (let index = 0; index < items.length; index += 1) {
    if (signal?.aborted) break;
    const item = items[index];
    onProgress({ done: index, total: items.length, current: item.worksheetNo });
    try {
      const { bytes, pdfId, backupStatus, backupError } = await pdfForRecord(workflow, item.recordKey, item.worksheetNo, presetMethod, drafts[item.recordKey]);
      /* Load once here to learn the page count and to fail early on a
         corrupt file, rather than at merge time with the dialog already up. */
      const source = await PDFDocument.load(bytes);
      parts.push({
        recordKey: item.recordKey,
        worksheetNo: item.worksheetNo,
        bytes,
        pageCount: source.getPageCount(),
        pdfId,
        backupStatus,
        backupError
      });
    } catch (reason) {
      if (reason instanceof BatchConflictError) {
        conflicts.push(reason.conflict);
        continue;
      }
      skipped.push({
        worksheetNo: item.worksheetNo,
        reason: reason instanceof Error ? reason.message : 'it could not be rendered'
      });
    }
  }

  onProgress({ done: items.length, total: items.length, current: '' });
  return { parts, skipped, conflicts };
}

/** Retry one queued worksheet only after its conflict was explicitly reviewed. */
export async function replaceBatchConflict(
  workflow: Workflow,
  item: BatchItem,
  presetMethod: string | undefined,
  draft: Record<string, string>,
  conflict: BatchConflict,
): Promise<BatchPart> {
  const { bytes, pdfId, backupStatus, backupError } = await pdfForRecord(workflow, item.recordKey, item.worksheetNo, presetMethod, draft, {
    requestedPdfId: conflict.requestedPdfId,
    existingPdfIds: conflict.existingPdfIds
  });
  const source = await PDFDocument.load(bytes);
  return {
    recordKey: item.recordKey,
    worksheetNo: item.worksheetNo,
    bytes,
    pageCount: source.getPageCount(),
    pdfId,
    backupStatus,
    backupError
  };
}

/** Stitches the chosen parts, in the order given, into one document. */
export async function mergeParts(parts: BatchPart[]): Promise<Blob | null> {
  if (!parts.length) return null;
  const merged = await PDFDocument.create();
  for (const part of parts) {
    const source = await PDFDocument.load(part.bytes);
    const pages = await merged.copyPages(source, source.getPageIndices());
    pages.forEach((page) => merged.addPage(page));
  }
  const bytes = await merged.save();
  /* Copy into a fresh buffer: pdf-lib returns a view over its own memory. */
  const copy = new Uint8Array(bytes.length);
  copy.set(bytes);
  return new Blob([copy], { type: 'application/pdf' });
}
