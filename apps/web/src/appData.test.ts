import { describe, expect, it } from 'vitest';
import { activeBinders, binderById, binderInstances, buildingGroups, fellerCorrected, listRoute, shelfBinders, tools, workflowById } from './appData';
import { catalogIndexUsable, cvSamplingFamily, normalizeCvTestMethod, pdfAvailability, pdfRouteForRecord } from './recordPolicy';
import { READ_CACHE_DB_NAME } from './storage';

describe('laboratory workflow policies', () => {
  it('calculates the tested Feller correction', () => {
    expect(fellerCorrected(35)).toBe(37);
    expect(fellerCorrected(120)).toBe(142);
    expect(fellerCorrected(260)).toBe(419);
  });

  it('uses a separate read-only cache namespace', () => {
    expect(READ_CACHE_DB_NAME).toBe('anf3-read-cache-v1');
  });

  /* Other preserves the orange physical family but is split by domain so a
     reader never enters an ambiguous mixed-work binder. */
  it('derives the shelf from the typed matrix registry', () => {
    expect(binderInstances).toHaveLength(18);
    expect(new Set(binderInstances.map((binder) => binder.id)).size).toBe(18);
    expect(activeBinders('B10')).toHaveLength(4);
    expect(activeBinders('B12')).toHaveLength(4);
    expect(activeBinders('B16')).toHaveLength(5);
    expect(activeBinders('OTHER')).toHaveLength(4);
    expect(binderInstances.filter((binder) => binder.state === 'active').every((binder) => binder.route)).toBe(true);
  });

  it('keeps the reserve binder on the shelf but never openable', () => {
    const reserve = binderById('reserve-spare');
    expect(reserve?.state).toBe('coming-soon');
    expect(reserve?.route).toBeNull();
    expect(reserve?.spine.code).toBe('COMING SOON');
    expect(buildingGroups.find((group) => group.id === 'RESERVE')?.active).toBe(false);
    expect(activeBinders('RESERVE')).toHaveLength(0);
    expect(shelfBinders('RESERVE')).toHaveLength(1);
  });

  it('splits Other into Water, Air, CA and CV binders without exposing storage shards', () => {
    expect(activeBinders('OTHER').map((binder) => binder.id))
      .toEqual(['other-water', 'other-air', 'other-ca', 'other-cv']);
    expect(binderById('other-water')?.route).toBe('/binder/other-water');
    expect(binderById('other-air')?.route).toContain('workflow=em-air');
    expect(binderById('other-ca')?.route).toContain('workflow=compressed-air');
    expect(binderById('other-cv')?.route).toContain('workflow=cv');
    expect(binderById('other-water')?.sections?.map((section) => section.route)).toEqual([
      '/list?building=Other&workflow=pw-prw&waterType=all',
      '/list?building=Other&workflow=wfi-pus&waterType=WFI%2FPUS'
    ]);
  });

  it('preserves binder work and secondary scope in list routes', () => {
    expect(binderById('b10-em-air')?.route).toBe('/list?building=Building+10&workflow=em-air');
    expect(binderById('b10-ca')?.route).toBe('/list?building=Building+10&workflow=compressed-air&gasType=CA');
    expect(listRoute('Other', 'pw-prw', { waterType: 'all' })).toBe('/list?building=Other&workflow=pw-prw&waterType=all');
  });

  it('keeps the unified list as the building-scoped entry point for each domain', () => {
    expect(binderById('b10-em-air')?.route).toContain('building=Building+10');
    expect(binderById('b10-em-air')?.route).toContain('workflow=em-air');
  });

  it('names the five required tool tabs and marks the one behind the lab network', () => {
    expect(tools.map((tool) => tool.label))
      .toEqual(['Stock DB', 'Stock Web', 'จองเลขเอกสาร', 'Upload Picture', 'COA App']);
    const coa = tools.find((tool) => tool.label === 'COA App');
    expect(coa?.href).toBe('http://192.168.1.10:8000');
    expect(coa?.network).toBe('ANF3');
    expect(tools.filter((tool) => tool.network)).toHaveLength(1);
  });

  it('requires a fresh online record before PDF generation', () => {
    const water = workflowById('pw-prw')!;
    expect(pdfAvailability(water, {}, true, true)).toEqual({ enabled: true, reason: 'ready' });
    expect(pdfAvailability(water, {}, false, true)).toEqual({ enabled: false, reason: 'stale' });
    expect(pdfAvailability(water, {}, true, false)).toEqual({ enabled: false, reason: 'offline' });
  });

  it('routes CV Contact and Rinse records through explicit method-aware routes', () => {
    const cv = workflowById('cv')!;
    const contact = { sampleMatrix: 'CONTACT_PLATE' };
    const rinse = { sampleMatrix: 'Rinse Test' };
    expect(cvSamplingFamily(contact)).toBe('contact-plate');
    expect(cvSamplingFamily(rinse)).toBe('rinse');
    expect(normalizeCvTestMethod('Memb. Filtration')).toBe('membrane-filtration');
    expect(pdfAvailability(cv, contact, true, true)).toEqual({ enabled: true, reason: 'ready' });
    expect(pdfAvailability(cv, rinse, true, true)).toEqual({ enabled: false, reason: 'method-required' });
    expect(pdfRouteForRecord(cv, rinse, 'pour-plate')).toBe('cleaning-validation-rinse-pour');
    expect(pdfRouteForRecord(cv, rinse, 'membrane-filtration')).toBe('cleaning-validation-rinse-membrane');
    expect(pdfAvailability(cv, rinse, true, true, 'pour-plate')).toEqual({ enabled: true, reason: 'ready' });
  });

  it('uses the catalog index only when its hash is accepted', () => {
    expect(catalogIndexUsable({ indexAvailable: true, hashMatches: true })).toBe(true);
    expect(catalogIndexUsable({ indexAvailable: true, hashMatches: false })).toBe(false);
    expect(catalogIndexUsable({ indexAvailable: false, hashMatches: true })).toBe(false);
  });
});
