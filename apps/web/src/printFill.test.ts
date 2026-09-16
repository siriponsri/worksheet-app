import { describe, expect, it } from 'vitest';
import { blankPayloadKeys, bulkSafeFields, initialPrintFillValue, mergePrintFill, printFieldLabel, printableFields } from './printFill';

describe('print fill contract', () => {
  it('accepts editable canonical payload keys without changing System DB data', () => {
    const payload = { floor: '', gradeControl: '', samplingDate: '01 Sep 2026' };
    expect(blankPayloadKeys(payload)).toEqual(['floor', 'gradeControl']);
    expect(mergePrintFill(payload, { floor: '2', gradeControl: 'D', samplingDate: 'wrong', templatePath: 'bad' }))
      .toEqual({ floor: '2', gradeControl: 'D', samplingDate: 'wrong' });
  });

  it('presents printable fields without internal DOCX names', () => {
    const fields = printableFields({ resultAvg01: '', lotMembrane: '', samplingPoint01: '', sampleCount: '1' });
    expect(fields.map((field) => field.label)).toEqual(['Membrane lot', 'Sampling point 01', 'Average result 01']);
    expect(fields.map((field) => field.label).join(' ')).not.toMatch(/resultAvg|lotMembrane|sampleCount/);
  });

  it('uses the selected document route to reject unrelated payload fields', () => {
    const fields = printableFields({ resultAvg01: '', result01: '', templatePayload: '', sampleCount: '1' }, 'wfi-pus');
    expect(fields.map((field) => field.label)).toEqual(['Result 01']);
    expect(fields.map((field) => field.label).join(' ')).not.toMatch(/templatePayload|sampleCount|Average/);
  });

  it('locks worksheet identity and maps legacy conflict aliases to human labels', () => {
    const payload = { docNo: 'PW-26-0001', building: 'Building 10', productName: 'Water', resultAvg01: '' };
    const fields = printableFields(payload, 'pw-prw');
    expect(fields.find((field) => field.key === 'docNo')?.editable).toBe(false);
    expect(fields.find((field) => field.key === 'building')?.editable).toBe(false);
    expect(mergePrintFill(payload, { building: 'Other', resultAvg01: 'TNTC' }, 'pw-prw')).toEqual({
      ...payload,
      resultAvg01: 'TNTC'
    });
    expect(printFieldLabel('ProductName', fields)).toBe('Product');
    expect(printFieldLabel('analyst', fields)).toBe('Analyst');
    expect(printFieldLabel('templatePayload', fields)).toBe('Other reviewed values');
  });

  it('shows Incubation No. blank until the operator supplies a print draft', () => {
    const payload = { docNo: 'PW-26-0001', building: 'Building 10', incNo: 'system-value' };
    const field = printableFields(payload, 'pw-prw').find((entry) => entry.key === 'incNo')!;
    expect(field.label).toBe('Incubation No.');
    expect(initialPrintFillValue(field, payload)).toBe('');
    expect(initialPrintFillValue(field, payload, { incNo: 'INC-01' })).toBe('INC-01');
    expect(mergePrintFill(payload, {}, 'pw-prw').incNo).toBe('');
    expect(mergePrintFill(payload, { incNo: 'INC-01' }, 'pw-prw').incNo).toBe('INC-01');
  });

  it('keeps batch-safe fields explicitly allowlisted', () => {
    const payload = { docNo: 'PW-26-0001', building: 'Building 10', incNo: '', lotTSA: '', resultAvg01: '', samplingPoint01: '' };
    expect(bulkSafeFields(payload, 'pw-prw').map((field) => field.key)).toEqual(['lotTSA']);
  });

  it('keeps every controlled route on its own human presentation schema', () => {
    const payload = {
      docNo: 'FIXTURE', building: 'Building 10', samplingDate: '01 Sep 2026', performedDate: '',
      productName: 'Fixture product', ProductName: 'Fixture product', sectionName: '', samplingTime: '',
      lotTSA: '', lotPCA: '', lotPlate: '', lotPipette: '', lotMembrane: '', lotForceps: '', lotBuffer: '',
      lotContact: '', lotNo: '', lotOther: '', lotMedia: '', mfgMedia: '', expMedia: '', gradeControl: '',
      negativeValue: '', comment: '', determinedDate: '', concludedDate: '', approvedDate: '', incNo: '',
      leftEM: '', rightEM: '', leftEm: '', rightEm: '', leftHand: '', rightHand: '', floor: '', temp: '', tempRoom01: '',
      samplingPoint01: 'Point', tagNo01: '', result101: '', result201: '', resultAvg01: '', result01: '',
      Grade01: '', grade01: '', rhRoom01: '', timeIn01: '', timeOut01: '', occurResult01: '',
      roomNo01: '', temp01: '', rh01: '', occResult01: '', remark01: ''
    };
    const routes = [
      ['pw-prw', ['Average result 01', 'Result I 01', 'Sampling point 01']],
      ['wfi-pus', ['Result 01', 'Membrane lot']],
      ['em-air', ['Result 01', 'Sample humidity 01', 'Floor']],
      ['compressed-air', ['Result 01', 'Sample temperature 01']],
      ['cleaning-validation-contact', ['Product', 'Grade 01', 'Result 01']],
      ['cleaning-validation-rinse-pour', ['Average result 01', 'Result II 01']],
      ['cleaning-validation-rinse-membrane', ['Result 01', 'Membrane lot']]
    ] as const;
    for (const [route, expected] of routes) {
      const labels = printableFields(payload, route).map((field) => field.label);
      for (const label of expected) expect(labels).toContain(label);
      expect(labels.join(' ')).not.toMatch(/samplesJson|templatePayload|resultAvg|lotPMembrane|leftEM/);
      if (route === 'cleaning-validation-contact') {
        expect(labels).not.toContain('Sample tag 01');
        expect(labels).not.toContain('Concluded date');
      }
    }
  });
});
