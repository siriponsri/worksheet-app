import type { Domain, WorkflowId } from './appData';

export type WorksetPhase = 'idle' | 'browsing' | 'selecting' | 'filling' | 'ready' | 'rendering' | 'previewing' | 'completed' | 'partial-failure';
export type WorksetItemStatus = 'not-reviewed' | 'draft-changed' | 'ready' | 'rendered' | 'failed';

export type WorksetItem = {
  domain: Domain;
  workflow: WorkflowId;
  recordKey: string;
  worksheetNo: string;
  scope: string;
  returnTo?: string;
  cvMethod?: string;
  status: WorksetItemStatus;
  failureReason?: string;
};

export type WorksetRender = { done: number; total: number; current: string; status: 'idle' | 'running' | 'complete' };
export type WorksetPreviewArtifact = { recordKey: string; worksheetNo: string; pdfId?: string; pageCount?: number; backupStatus?: 'succeeded' | 'pending' | 'disabled' | 'failed'; backupError?: string };
export type WorksetState = {
  scopeKey: string;
  building: string;
  domain: Domain;
  workflow: WorkflowId;
  cvMethod?: string;
  returnTo?: string;
  phase: WorksetPhase;
  visibleRecordKeys: string[];
  items: WorksetItem[];
  drafts: Record<string, Record<string, string>>;
  render: WorksetRender;
  previewArtifacts: WorksetPreviewArtifact[];
};

export const WORKSET_STORAGE_KEY = 'anf3.workset.v1';
export const WORKSET_EVENT = 'anf3:workset';
const LEGACY_QUEUE_STORAGE_KEY = 'anf3.print-queue.v1';

function token(value: unknown) {
  return String(value || '').trim().toLowerCase().replace(/[\s_.-]+/g, '-');
}

export function worksetScopeKey(domain: Domain, workflow: WorkflowId, building: string, cvMethod = '') {
  return [domain, workflow, token(building) || 'all', token(cvMethod)].join(':');
}

export function worksetItemKey(item: Pick<WorksetItem, 'domain' | 'workflow' | 'recordKey'>) {
  return `${item.domain}:${item.workflow}:${item.recordKey}`;
}

export function createWorkset(item: Omit<WorksetItem, 'status'>, visibleRecordKeys: string[] = []): WorksetState {
  return {
  scopeKey: worksetScopeKey(item.domain, item.workflow, item.scope, item.cvMethod), building: item.scope,
    domain: item.domain, workflow: item.workflow, cvMethod: item.cvMethod, returnTo: item.returnTo, phase: 'selecting',
    visibleRecordKeys: [...visibleRecordKeys], items: [{ ...item, status: 'not-reviewed' }], drafts: {},
    render: { done: 0, total: 0, current: '', status: 'idle' }, previewArtifacts: []
  };
}

export function isWorksetInScope(state: WorksetState | null, scopeKey: string) {
  return Boolean(state && state.scopeKey === scopeKey);
}

export function addWorksetItem(state: WorksetState | null, item: Omit<WorksetItem, 'status'>, visibleRecordKeys: string[] = []) {
  if (!state) return createWorkset(item, visibleRecordKeys);
  if (state.scopeKey !== worksetScopeKey(item.domain, item.workflow, item.scope, item.cvMethod)) return state;
  if (state.items.some((candidate) => worksetItemKey(candidate) === worksetItemKey(item))) return state;
  return { ...state, phase: 'selecting' as const, visibleRecordKeys: [...visibleRecordKeys], items: [...state.items, { ...item, status: 'not-reviewed' as const }] };
}

export function removeWorksetItem(state: WorksetState | null, item: Pick<WorksetItem, 'domain' | 'workflow' | 'recordKey'>) {
  if (!state) return null;
  const items = state.items.filter((candidate) => worksetItemKey(candidate) !== worksetItemKey(item));
  return items.length ? { ...state, phase: 'selecting' as const, items } : null;
}

export function setWorksetVisibleRecords(state: WorksetState | null, visibleRecordKeys: string[]) {
  return state ? { ...state, visibleRecordKeys: [...visibleRecordKeys] } : null;
}

export function setWorksetDraft(state: WorksetState | null, recordKey: string, draft: Record<string, string>): WorksetState | null {
  if (!state) return null;
  const items = state.items.map((item) => item.recordKey === recordKey
    ? { ...item, status: item.status === 'rendered' ? 'draft-changed' as const : item.status }
    : item);
  return { ...state, phase: 'filling' as const, items, drafts: { ...state.drafts, [recordKey]: { ...draft } } };
}

export function setWorksetItemStatus(state: WorksetState | null, recordKey: string, status: WorksetItemStatus, failureReason?: string): WorksetState | null {
  if (!state) return null;
  return { ...state, items: state.items.map((item) => item.recordKey === recordKey
    ? { ...item, status, failureReason: status === 'failed' ? failureReason || 'The worksheet could not be rendered.' : undefined }
    : item) };
}

export function setWorksetRender(state: WorksetState | null, render: Partial<WorksetRender>) {
  return state ? { ...state, phase: render.status === 'running' ? 'rendering' as const : state.phase, render: { ...state.render, ...render } } : null;
}

export function setWorksetPhase(state: WorksetState | null, phase: WorksetPhase) {
  return state ? { ...state, phase } : null;
}

export function setWorksetPreview(state: WorksetState | null, previewArtifacts: WorksetPreviewArtifact[], partialFailure = false) {
  return state ? { ...state, phase: partialFailure ? 'partial-failure' as const : 'completed' as const, previewArtifacts: [...previewArtifacts] } : null;
}

export function updateWorksetPreviewArtifact(state: WorksetState | null, recordKey: string, patch: Partial<WorksetPreviewArtifact>) {
  if (!state) return null;
  return {
    ...state,
    previewArtifacts: state.previewArtifacts.map((artifact) => artifact.recordKey === recordKey
      ? { ...artifact, ...patch }
      : artifact)
  };
}

export function worksetIsReady(state: WorksetState | null, validate: (item: WorksetItem) => boolean = () => true) {
  return Boolean(state?.items.length && state.items.every((item) =>
    (item.status === 'ready' || item.status === 'draft-changed') && validate(item)
  ));
}

export function worksetStatusCounts(state: WorksetState | null) {
  const counts: Record<WorksetItemStatus, number> = { 'not-reviewed': 0, 'draft-changed': 0, ready: 0, rendered: 0, failed: 0 };
  state?.items.forEach((item) => { counts[item.status] += 1; });
  return counts;
}

function validItem(value: unknown): value is WorksetItem {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<WorksetItem>;
  return Boolean(item.domain && item.workflow && item.recordKey && item.worksheetNo && item.scope
    && ['not-reviewed', 'draft-changed', 'ready', 'rendered', 'failed'].includes(item.status || ''));
}

function validState(value: unknown): value is WorksetState {
  if (!value || typeof value !== 'object') return false;
  const state = value as Partial<WorksetState>;
  return Boolean(state.scopeKey && state.building && state.domain && state.workflow
    && ['idle', 'browsing', 'selecting', 'filling', 'ready', 'rendering', 'previewing', 'completed', 'partial-failure'].includes(state.phase || '')
    && Array.isArray(state.items) && state.items.every(validItem)
    && Array.isArray(state.visibleRecordKeys)
    && state.drafts && typeof state.drafts === 'object'
    && state.render && typeof state.render === 'object'
    && Array.isArray(state.previewArtifacts));
}

export function readWorkset(): WorksetState | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(WORKSET_STORAGE_KEY) || 'null');
    return validState(value) ? value : null;
  } catch { return null; }
}

export function writeWorkset(state: WorksetState | null) {
  try {
    if (state) sessionStorage.setItem(WORKSET_STORAGE_KEY, JSON.stringify(state));
    else sessionStorage.removeItem(WORKSET_STORAGE_KEY);
  } catch { /* in-memory callers still retain the state */ }
  window.dispatchEvent(new CustomEvent(WORKSET_EVENT));
  return state;
}

export function clearWorkset() { writeWorkset(null); }

/** Migrate the former queue storage once, without keeping its selection API alive. */
export function migrateLegacyWorkset(): WorksetState | null {
  const current = readWorkset();
  if (current) return current;
  try {
    const parsed = JSON.parse(sessionStorage.getItem(LEGACY_QUEUE_STORAGE_KEY) || '[]');
    if (!Array.isArray(parsed) || !parsed.length) return null;
    const valid = parsed.filter((value): value is Omit<WorksetItem, 'status'> => {
      if (!value || typeof value !== 'object') return false;
      const item = value as Partial<WorksetItem>;
      return Boolean(item.domain && item.workflow && item.recordKey && item.worksheetNo && item.scope);
    });
    if (!valid.length) return null;
    const first = valid[0];
    const visible = valid.map((item) => item.recordKey);
    const migrated = valid.slice(1).reduce(
      (state, item) => addWorksetItem(state, item, visible),
      createWorkset(first, visible)
    );
    writeWorkset(migrated);
    sessionStorage.removeItem(LEGACY_QUEUE_STORAGE_KEY);
    return migrated;
  } catch {
    return null;
  }
}
