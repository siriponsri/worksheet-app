import { describe, expect, it } from 'vitest';
import { addWorksetItem, createWorkset, removeWorksetItem, setWorksetDraft, setWorksetItemStatus, setWorksetPhase, setWorksetPreview, updateWorksetPreviewArtifact, worksetIsReady, worksetItemKey, worksetScopeKey } from './workset';

const first = { domain: 'cv' as const, workflow: 'cv' as const, recordKey: 'a', worksheetNo: 'CV-26-B16-0001', scope: 'Building 16', cvMethod: 'membrane-filtration' };

describe('operator workset state', () => {
  it('keeps one compatible scope and selection order', () => {
    let state = createWorkset(first, ['a', 'b']);
    state = addWorksetItem(state, { ...first, recordKey: 'b', worksheetNo: 'CVR-26-B16-0002' }, ['a', 'b'])!;
    expect(state.scopeKey).toBe(worksetScopeKey('cv', 'cv', 'Building 16', 'membrane-filtration'));
    expect(state.items.map((item) => item.recordKey)).toEqual(['a', 'b']);
    expect(worksetItemKey(state.items[0])).toBe('cv:cv:a');
    expect(addWorksetItem(state, { ...first, recordKey: 'other', scope: 'Building 10' })).toBe(state);
  });
  it('removes the requested item and clears an empty set', () => {
    expect(removeWorksetItem(createWorkset(first), { domain: 'cv', workflow: 'cv', recordKey: 'a' })).toBeNull();
  });
  it('tracks local drafts and readiness without changing item identity', () => {
    let state = setWorksetDraft(createWorkset(first), 'a', { performedDate: '15 Sep 2026' })!;
    expect(state.drafts.a).toEqual({ performedDate: '15 Sep 2026' });
    expect(state.items[0].status).toBe('not-reviewed');
    expect(worksetIsReady(state)).toBe(false);
    expect(worksetIsReady(state, () => false)).toBe(false);
    state = setWorksetItemStatus(state, 'a', 'ready')!;
    expect(worksetIsReady(state)).toBe(true);
    expect(worksetIsReady(state, () => true)).toBe(true);
  });
  it('retains successful preview artifacts alongside failures', () => {
    let state = setWorksetItemStatus(createWorkset(first), 'a', 'failed', 'No approved route')!;
    state = setWorksetPreview(state, [{ recordKey: 'b', worksheetNo: 'CVR-26-B16-0002', pageCount: 2 }], true)!;
    expect(state.phase).toBe('partial-failure');
    expect(state.items[0].failureReason).toBe('No approved route');
    expect(state.previewArtifacts[0].worksheetNo).toBe('CVR-26-B16-0002');
    state = updateWorksetPreviewArtifact(state, 'b', { pdfId: 'pdf-1', backupStatus: 'pending', backupError: 'share unavailable' })!;
    expect(state.previewArtifacts[0].backupStatus).toBe('pending');
    expect(state.previewArtifacts[0].backupError).toBe('share unavailable');
  });
  it('keeps the return route and explicit phase transitions in the workset', () => {
    let state = createWorkset({ ...first, returnTo: '/list?building=Building+16&workflow=cv' });
    expect(state.returnTo).toContain('/list?building=');
    state = setWorksetPhase(state, 'previewing')!;
    expect(state.phase).toBe('previewing');
    state = setWorksetPhase(state, 'idle')!;
    expect(state.phase).toBe('idle');
  });
});
