import type { RecordData } from './storage';

function text(value: unknown) { return value == null ? '' : String(value); }

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * Every date in every controlled document is date-only, `dd MMM yyyy`
 * ("01 Sep 2026").
 *
 * This used to emit `DD/MM/YYYY` while the legacy print pages emitted
 * `DD Mon YYYY` from `formatDateDMY()` in `js/utils.js` — two formats for the
 * same field on the same controlled worksheet, decided by nothing more than
 * which page printed it. This function is the React-side half of closing that
 * gap, so keep the two in step if either changes.
 *
 * A `YYYY-MM-DD` string is split rather than passed through `new Date()`: the
 * Date constructor reads a bare ISO date as UTC midnight, which in Bangkok
 * renders as the previous day.
 */
function date(value: unknown) {
  const raw = text(value).trim();
  if (!raw) return '';

  /* Already the target format. */
  if (/^\d{2}\s[A-Za-z]{3}\s\d{4}$/.test(raw)) return raw;

  const build = (year: number, month: number, day: number) => {
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return raw;
    if (month < 1 || month > 12 || day < 1 || day > 31) return raw;
    return `${String(day).padStart(2, '0')} ${MONTHS[month - 1]} ${year}`;
  };

  /* What the System DB normalises samplingDate and performedDate to. Any time
     part is dropped rather than rendered. */
  const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return build(Number(iso[1]), Number(iso[2]), Number(iso[3]));

  const dmy = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (dmy) return build(Number(dmy[3]), Number(dmy[2]), Number(dmy[1]));

  const dashed = raw.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (dashed) return build(Number(dashed[3]), Number(dashed[2]), Number(dashed[1]));

  /* A Sheets serial date, which arrives when a cell was never formatted. */
  if (/^\d+(\.\d+)?$/.test(raw)) {
    const at = new Date(Date.UTC(1899, 11, 30) + Number(raw) * 86400000);
    if (!Number.isNaN(at.getTime())) return build(at.getUTCFullYear(), at.getUTCMonth() + 1, at.getUTCDate());
  }

  /* Unrecognised: pass it through rather than invent a date. */
  return raw;
}

/**
 * A microbial count, to nought decimal places.
 *
 * These are the semantics `formatResultValue()` in `js/utils.js` has always
 * used on the legacy pages, kept here so one worksheet reads the same
 * whichever path printed it:
 *
 *   - blank stays blank — an unfilled cell must never become a number
 *   - a genuine zero is reported as `<1`, the limit of detection, not as "0"
 *   - anything else is rounded UP, the conservative direction for a count
 *     that a limit is judged against
 *   - a non-numeric entry (`TNTC`, a note) passes through untouched
 */
function count(value: unknown) {
  const raw = text(value).trim();
  if (!raw) return '';
  const num = Number.parseFloat(raw);
  if (Number.isNaN(num)) return raw;
  if (num === 0) return '<1';
  return String(Math.ceil(num));
}

/**
 * A measured quantity — temperature, relative humidity — to nought decimal
 * places. Rounded to nearest, NOT ceiling: a reading is not a count, so
 * rounding it up would overstate it, and `<1` has no meaning for one, which
 * is why a measured zero stays "0".
 */
function measure(value: unknown) {
  const raw = text(value).trim();
  if (!raw) return '';
  const num = Number.parseFloat(raw);
  if (Number.isNaN(num)) return raw;
  return String(Math.round(num));
}

/**
 * The first of several aliases that actually carries a value.
 *
 * `a || b` treats a genuine `0` as absent, which on a count means a plate with
 * no growth falls through to the next alias and ends up blank. On a controlled
 * worksheet a blank cell reads as "not tested" while `<1` reads as "tested,
 * nothing found" — so the difference matters more here than the brevity does.
 */
function firstOf(...values: unknown[]) {
  return values.find((value) => value !== null && value !== undefined && value !== '');
}

function samplesOf(record: RecordData, samples: RecordData[]) {
  return samples.length ? samples : (Array.isArray(record.samples) ? record.samples as RecordData[] : []);
}

export function templateSampleCapacity(workflow: string) {
  if (workflow === 'em-air') return 50;
  if (workflow === 'compressed-air' || workflow === 'cleaning-validation-contact') return 10;
  return 30;
}

function header(record: RecordData, worksheetNo: string) {
  return {
    /* The queued worksheet identity is authoritative. A stale cached record
       must not put a different header number into a document named for the
       queue item. */
    docNo: text(worksheetNo), building: text(record.building),
    ProductName: text(record.productName || record.ProductName),
    productName: text(record.productName || record.ProductName),
    samplingDate: date(record.samplingDate), performedDate: date(record.performedDate),
    determinedDate: date(record.determinedDate), concludedDate: date(record.concludedDate), approvedDate: date(record.approvedDate),
    temp: text(record.temp),
    /* Incubation No. is a print-time operator field. It must never inherit an
       internal value from the read-only System DB record; an explicit local
       draft is merged later by printFill.ts. */
    incNo: '', comment: text(record.comment),
    /* The control plate on a Cleaning Validation Contact worksheet. Missing
       here until now, which printed the literal text `<gradeControl>` on every
       one of them: the server only substitutes keys it is sent, so a key that
       is never sent is never even blanked. */
    gradeControl: text(record.gradeControl),
    rightEM: text(record.rightEM), leftEM: text(record.leftEM), rightEm: text(record.rightEm || record.rightEM), leftEm: text(record.leftEm || record.leftEM),
    rightHand: text(record.rightHand), leftHand: text(record.leftHand), negativeValue: text(record.negativeValue),
    lotTSA: text(record.lotTSA), lotPCA: text(record.lotPCA), lotPlate: text(record.lotPlate), lotPipette: text(record.lotPipette),
    lotMembrane: text(record.lotMembrane || record.lotPMembrane), lotForceps: text(record.lotForceps), lotBuffer: text(record.lotBuffer), lotOther: text(record.lotOther),
    lotMedia: text(record.lotMedia), mfgMedia: text(record.mfgMedia), expMedia: text(record.expMedia),
    lotNo: text(record.lotNo), sectionName: text(record.sectionName), samplingTime: text(record.samplingTime), 'samplingTime ': text(record.samplingTime), lotContact: text(record.lotContact)
  };
}

export function documentPayload(workflow: string, record: RecordData, samples: RecordData[], worksheetNo: string, method?: string) {
  const payload: Record<string, string> = { ...header(record, worksheetNo) };
  if (workflow.startsWith('cleaning-validation-')) {
    payload.testMethod = text(method || record.testMethod);
    payload.samplingFamily = text(record.samplingFamily || record.sampleMatrix);
  }
  const rows = samplesOf(record, samples);
  payload.sampleCount = String(rows.length);
  /* The floor the room is on. Record-level when it is set, otherwise taken
     from the first sample, which is where the source sheet carries it — the
     same derivation as `js/print-em-air.js:363`. Unfilled until now, so the EM
     template printed the literal `<floor>` on every worksheet. */
  payload.floor = text(record.floor || rows[0]?.floor);
  const limit = templateSampleCapacity(workflow);
  if (workflow === 'compressed-air') payload.tempRoom01 = measure(record.temp);

  /* CV Rinse keeps the source contract intact. A sampling point is not a tag,
     and historical results must never be cleared while preparing a document. */
  const rinse = workflow === 'cleaning-validation-rinse-pour' || workflow === 'cleaning-validation-rinse-membrane';

  for (let i = 1; i <= limit; i += 1) {
    const suffix = String(i).padStart(2, '0');
    const sample = rows[i - 1] || {};
    const point = workflow === 'cleaning-validation-contact'
      ? [sample.equipment, sample.location].filter(Boolean).join(' - ')
      : text(sample.samplingPoint || sample.roomNo || sample.room || sample.location);

    if (rinse) {
      payload[`tagNo${suffix}`] = text(sample.tagNo || sample.samplingTag);
      payload[`samplingPoint${suffix}`] = '';
    } else {
      payload[`samplingPoint${suffix}`] = point;
      payload[`tagNo${suffix}`] = text(sample.samplingTag || sample.tagNo);
    }

    if (workflow === 'cleaning-validation-rinse-pour') {
      payload[`result1${suffix}`] = '';
      payload[`result2${suffix}`] = '';
      payload[`resultAvg${suffix}`] = count(firstOf(sample.resultAvg, sample.resultDisplay));
    } else if (workflow === 'cleaning-validation-rinse-membrane') {
      payload[`result${suffix}`] = count(firstOf(sample.result, sample.resultDisplay));
    } else if (workflow === 'pw-prw' || method === 'pour-plate') {
      payload[`result1${suffix}`] = count(sample.result1);
      payload[`result2${suffix}`] = count(sample.result2);
      payload[`resultAvg${suffix}`] = count(sample.resultAvg);
    } else if (workflow === 'wfi-pus' || method === 'membrane-filtration') {
      payload[`result${suffix}`] = count(sample.result);
    } else if (workflow === 'cleaning-validation-contact') {
      payload[`Grade${suffix}`] = text(sample.grade);
      payload[`result${suffix}`] = count(firstOf(sample.result, sample.resultValue, sample.resultDisplay));
    } else if (workflow === 'em-air') {
      payload[`roomNo${suffix}`] = point; payload[`grade${suffix}`] = text(sample.grade);
      payload[`tempRoom${suffix}`] = measure(sample.tempRoom); payload[`rhRoom${suffix}`] = measure(sample.rhRoom);
      payload[`timeIn${suffix}`] = text(sample.timeIn); payload[`timeOut${suffix}`] = text(sample.timeOut);
      payload[`occurResult${suffix}`] = count(sample.occurResult); payload[`remark${suffix}`] = text(sample.remark);
    } else if (workflow === 'compressed-air') {
      payload[`roomNo${suffix}`] = point; payload[`grade${suffix}`] = text(sample.grade);
      payload[`temp${suffix}`] = measure(sample.temp); payload[`rh${suffix}`] = measure(sample.rh);
      payload[`occResult${suffix}`] = count(sample.occResult); payload[`remark${suffix}`] = text(sample.remark);
    }
  }
  return payload;
}

/**
 * Build the self-contained page dictionaries required by the PDF server.
 * Every page repeats the record/header fields and carries only its own sample
 * window; the server intentionally does not inherit top-level data into pages.
 */
export function documentPages(
  workflow: string,
  record: RecordData,
  samples: RecordData[],
  worksheetNo: string,
  method?: string
) {
  const rows = samplesOf(record, samples);
  const capacity = templateSampleCapacity(workflow);
  const pageCount = Math.max(1, Math.ceil(rows.length / capacity));
  return Array.from({ length: pageCount }, (_, pageIndex) => {
    const pageRows = rows.slice(pageIndex * capacity, (pageIndex + 1) * capacity);
    const page = documentPayload(workflow, record, pageRows, worksheetNo, method);
    page.sampleCount = String(rows.length);
    return page;
  });
}
