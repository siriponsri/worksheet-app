import type { RecordFilters } from './api';
import type { SearchItem } from './storage';

function token(value: unknown) {
  return String(value || '').trim().toLowerCase().replace(/[\s_.-]+/g, '');
}

/**
 * A building label reduced to its segment: `B10`, `B12`, `B16`, or `OTHER`.
 *
 * The `building` column is free text and every form of it exists in the live
 * data — `Building 12`, `B12`, `12`, `bldg-12` — because the System DB returns
 * the cell verbatim (`searchAirResponse_` does `record.building || ''`) and
 * only normalises when choosing which shard to write to. Comparing the labels
 * as whole strings therefore drops an entire binder silently whenever the
 * spelling drifts, with nothing on screen to say why.
 *
 * Anything unrecognised falls back to its own token, so an unexpected label
 * still matches itself instead of matching everything.
 */
export function buildingSegment(value: unknown) {
  const normalized = String(value || '').trim().toUpperCase().replace(/[\s_.-]+/g, '');
  const match = normalized.match(/^(?:BUILDING|BLDG|BLD|B)?(10|12|16)$/);
  return match ? `B${match[1]}` : 'OTHER';
}

/** Filter-only building parsing. Composite source text such as
 * `OSD-PW (Building 10)` must match B10, while unknown/blank values belong to
 * the physical Other shard without changing worksheet-number normalization. */
export function buildingFilterSegment(value: unknown) {
  const raw = String(value || '').trim().toUpperCase();
  const composite = raw.match(/(?:BUILDING|BLDG|BLD)\s*[-_:()]*\s*(10|12|16)\b/);
  const code = raw.match(/\bB\s*(10|12|16)\b/);
  const normalized = raw.replace(/[\s_.-]+/g, '');
  const direct = normalized.match(/^(?:BUILDING|BLDG|BLD|B)?(10|12|16)$/);
  const match = composite || code || direct;
  if (match) return `B${match[1]}`;
  return 'OTHER';
}

export function buildingFilterForApi(value: unknown) {
  const raw = String(value || '').trim();
  if (!raw || raw.toLowerCase() === 'all') return '';
  if (/^(?:other|other locations|ot)$/i.test(raw)) return 'Other';
  return raw;
}

export function buildingLabel(value: unknown) {
  const segment = buildingFilterSegment(value);
  if (segment === 'OTHER') return 'Other Locations';
  return `Building ${segment.slice(1)}`;
}

/** Splits a filter value that may carry several alternatives — the binder for
 *  Building 16 asks for `gasType=CA,N2` — into its parts. */
export function filterValues(value?: string) {
  return String(value || '').split(',').map((part) => part.trim()).filter(Boolean);
}

/** True when the item's value is any one of the alternatives asked for. */
function matchesAny(itemValue: unknown, filterValue: string | undefined) {
  const wanted = filterValues(filterValue);
  if (!wanted.length || wanted.includes('all')) return true;
  const actual = token(itemValue);
  return wanted.some((candidate) => token(candidate) === actual);
}

/* `gasType`, `waterType` and `samplingMode` stay in the signature because the
   callers pass whole filter objects, but they are NOT applied here: they
   describe the samples inside a record, and `SearchItem` carries no sample
   data to test them against. They are applied by the System DB, which has the
   samples — see the any-of match in `searchAirResponse_`. Filtering them here
   against a field that does not exist would drop every row. */
type ScopeFilters = Pick<RecordFilters, 'building' | 'samplingFamily' | 'testMethod' | 'gasType' | 'waterType' | 'samplingMode'>;

export function itemInRecordScope(item: SearchItem, filters: ScopeFilters) {
  if (filters.building) {
    const wanted = filterValues(filters.building).map(buildingFilterSegment);
    if (wanted.length && !wanted.includes(buildingFilterSegment(item.building))) return false;
  }
  if (filters.samplingFamily && filters.samplingFamily !== 'all') {
    const matrix = token(item.sampleMatrix);
    const family = token(filters.samplingFamily);
    if (family === 'contactplate' && !matrix.includes('contact')) return false;
    if (family === 'rinse' && !matrix.includes('rinse') && !matrix.includes('pw') && !matrix.includes('wfi')) return false;
  }
  if (filters.testMethod && !matchesAny(item.testMethod, filters.testMethod)) return false;
  return true;
}

export function filterRecordScope(items: SearchItem[], filters: ScopeFilters) {
  return items.filter((item) => itemInRecordScope(item, filters));
}

/** Apply the refinement filters locally when a cached scope is read offline. */
export function filterRecordList(items: SearchItem[], filters: Pick<RecordFilters, 'q' | 'from' | 'to'>) {
  const query = String(filters.q || '').trim().toLowerCase();
  return items.filter((item) => {
    const haystack = [item.worksheetNo, item.recordId, item.docNo, item.building, item.samplingDate,
      item.performedDate, item.samplingPoints, item.productName, item.sampleMatrix, item.testMethod,
      item.recordStatus, item.reviewStatus].filter(Boolean).join(' ').toLowerCase();
    if (query && !haystack.includes(query)) return false;
    if (filters.from && String(item.samplingDate || '') < filters.from) return false;
    if (filters.to && String(item.samplingDate || '') > filters.to) return false;
    return true;
  });
}
