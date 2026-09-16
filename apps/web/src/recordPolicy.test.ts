import { describe, expect, it } from 'vitest';
import { pdfRouteForRecord } from './recordPolicy';
import { workflows } from './appData';

const cv = workflows.find((workflow) => workflow.id === 'cv')!;

describe('CV route selection', () => {
  it('uses Test-Method for a Rinse-PW source record', () => {
    expect(pdfRouteForRecord(cv, { sampleMatrix: 'Rinse-PW', testMethod: 'MEMBRANE_FILTRATION' })).toBe('cleaning-validation-rinse-membrane');
  });

  it('keeps Contact Plate on the contact template', () => {
    expect(pdfRouteForRecord(cv, { sampleMatrix: 'CONTACT_PLATE', testMethod: 'Contact Plate' })).toBe('cleaning-validation-contact');
  });
});
