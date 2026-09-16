import { describe, expect, it } from 'vitest';
import { documentPages, documentPayload, templateSampleCapacity } from './documentPayload';

describe('documentPayload', () => {
  it('keeps Incubation No. blank even when System DB carries an internal value', () => {
    const payload = documentPayload('pw-prw', { incNo: 'INC-SYSTEM-DO-NOT-USE' }, [], 'WP-26-0001');
    expect(payload.incNo).toBe('');
  });

  it('maps WFI result and legacy membrane aliases', () => {
    const payload = documentPayload('wfi-pus', { worksheetNo: 'WP-26-0001', lotPMembrane: 'M-1' }, [{ samplingPoint: 'P1', result: 3 }], 'WP-26-0001');
    expect(payload.lotMembrane).toBe('M-1');
    expect(payload.samplingPoint01).toBe('P1');
    expect(payload.result01).toBe('3');
  });

  it('uses the queued worksheet identity when a cached record is stale', () => {
    const payload = documentPayload('pw-prw', { docNo: 'OLD-IDENTITY', worksheetNo: 'OLD-IDENTITY-2' }, [], 'WT-26-B10-0042');
    expect(payload.docNo).toBe('WT-26-B10-0042');
  });

  it('uses record temperature only for CA tempRoom01', () => {
    const payload = documentPayload('compressed-air', { temp: 22 }, [{ temp: 20 }], 'AC-26-B10-0001');
    expect(payload.tempRoom01).toBe('22');
    expect(payload.temp01).toBe('20');
    expect(payload.tempRoom02).toBeUndefined();
  });

  it('keeps Contact fields record-level and blank when absent', () => {
    const payload = documentPayload('cleaning-validation-contact', {
      productName: 'Risperidone',
      building: 'Building 16'
    }, [{ equipment: 'Filler', location: 'Needle 1', grade: 'D', result: 2 }], 'CV-26-B16-0001');
    expect(payload.ProductName).toBe('Risperidone');
    expect(payload.lotNo).toBe('');
    expect(payload.sectionName).toBe('');
    expect(payload.samplingTime).toBe('');
    expect(payload['samplingTime ']).toBe('');
    expect(payload.lotContact).toBe('');
    expect(payload.samplingPoint01).toBe('Filler - Needle 1');
  });

  /* The control plate. Absent from the payload until v7.2, which printed the
     literal `<gradeControl>` on every Contact Plate worksheet, because the
     server blanks only the keys it is actually sent. */
  describe('gradeControl', () => {
    it('is always present, so the token is never left on the page', () => {
      const filled = documentPayload('cleaning-validation-contact', { gradeControl: 'D' }, [], 'CV-26-B16-0001');
      expect(filled.gradeControl).toBe('D');

      const absent = documentPayload('cleaning-validation-contact', {}, [], 'CV-26-B16-0001');
      expect(absent.gradeControl).toBe('');
      expect(Object.prototype.hasOwnProperty.call(absent, 'gradeControl')).toBe(true);
    });
  });

  /* Every date on every controlled document is date-only, `dd MMM yyyy`. */
  describe('dates', () => {
    it('renders an ISO date as dd MMM yyyy', () => {
      const payload = documentPayload('pw-prw', { samplingDate: '2026-09-01', performedDate: '2026-09-02' }, [], 'WP-26-0001');
      expect(payload.samplingDate).toBe('01 Sep 2026');
      expect(payload.performedDate).toBe('02 Sep 2026');
    });

    it('drops a time part rather than rendering it', () => {
      const payload = documentPayload('pw-prw', { samplingDate: '2026-01-23T17:00:00.000Z' }, [], 'WP-26-0001');
      expect(payload.samplingDate).toBe('23 Jan 2026');
    });

    it('converts the old DD/MM/YYYY output and is idempotent', () => {
      expect(documentPayload('pw-prw', { samplingDate: '01/09/2026' }, [], 'W').samplingDate).toBe('01 Sep 2026');
      expect(documentPayload('pw-prw', { samplingDate: '01 Sep 2026' }, [], 'W').samplingDate).toBe('01 Sep 2026');
    });

    it('leaves blank blank and passes an unrecognised value through', () => {
      expect(documentPayload('pw-prw', {}, [], 'W').samplingDate).toBe('');
      expect(documentPayload('pw-prw', { samplingDate: 'not a date' }, [], 'W').samplingDate).toBe('not a date');
    });
  });

  /* Counts carry the same semantics as formatResultValue() in js/utils.js, so
     one worksheet reads the same whichever path printed it. */
  describe('numbers', () => {
    it('rounds a count up and reports a genuine zero as the detection limit', () => {
      const payload = documentPayload('pw-prw', {}, [{ result1: 2.1, result2: 0, resultAvg: 1.05 }], 'WP-26-0001');
      expect(payload.result101).toBe('3');
      expect(payload.result201).toBe('<1');
      expect(payload.resultAvg01).toBe('2');
    });

    it('leaves a blank count blank and passes TNTC through', () => {
      const payload = documentPayload('pw-prw', {}, [{ result1: '', result2: 'TNTC' }], 'WP-26-0001');
      expect(payload.result101).toBe('');
      expect(payload.result201).toBe('TNTC');
    });

    it('rounds a measured value to nearest and keeps a measured zero', () => {
      const payload = documentPayload('em-air', {}, [{ tempRoom: 22.4, rhRoom: 55.6 }], 'AT-26-B10-0001');
      expect(payload.tempRoom01).toBe('22');
      expect(payload.rhRoom01).toBe('56');
      expect(documentPayload('em-air', {}, [{ tempRoom: 0 }], 'A').tempRoom01).toBe('0');
    });
  });

  /* CV Rinse retains source results; a sampling point never manufactures a
     tag in the Water-family template. */
  describe('cleaning validation rinse', () => {
    it('keeps a real tag and average result for Pour Plate', () => {
      const payload = documentPayload('cleaning-validation-rinse-pour', { sampleMatrix: 'Rinse' }, [{ samplingPoint: 'Tank 1', resultAvg: 'TNTC' }], 'CVR-26-B16-0001');
      expect(payload.tagNo01).toBe('');
      expect(payload.samplingPoint01).toBe('');
      expect(payload.result101).toBe('');
      expect(payload.result201).toBe('');
      expect(payload.resultAvg01).toBe('TNTC');
    });

    it('keeps a real tag and result for Membrane Filtration', () => {
      const payload = documentPayload('cleaning-validation-rinse-membrane', { sampleMatrix: 'Rinse' }, [{ samplingPoint: 'Line 3', tagNo: 'TAG-3', result: 7 }], 'CVR-26-B16-0002');
      expect(payload.tagNo01).toBe('TAG-3');
      expect(payload.samplingPoint01).toBe('');
      expect(payload.result01).toBe('7');
    });

    it('does not move the point for a plain Water worksheet', () => {
      const payload = documentPayload('pw-prw', {}, [{ samplingPoint: 'P1', samplingTag: 'T1' }], 'WP-26-0001');
      expect(payload.samplingPoint01).toBe('P1');
      expect(payload.tagNo01).toBe('T1');
    });
  });
});

/* `a || b` reads a genuine 0 as absent. On a count that means a plate with no
   growth falls through the alias chain and prints blank, and a blank cell on a
   controlled worksheet reads as "not tested" rather than "nothing found". */
describe('a zero count survives the alias chain', () => {
  it('reports a Contact Plate zero as the detection limit', () => {
    const payload = documentPayload('cleaning-validation-contact', {}, [{ result: 0 }], 'CV-26-B16-0001');
    expect(payload.result01).toBe('<1');
  });

  it('still falls back to the aliases when the result is genuinely absent', () => {
    expect(documentPayload('cleaning-validation-contact', {}, [{ resultDisplay: 'TNTC' }], 'C').result01).toBe('TNTC');
    expect(documentPayload('cleaning-validation-contact', {}, [{}], 'C').result01).toBe('');
  });
});

describe('normalized CV System DB records keep source-shaped mappings', () => {
  const sourceRecord = {
    worksheetNo: 'CVR-26-B16-0042',
    sampleMatrix: 'Rinse-PW',
    samplingFamily: 'rinse',
    testMethod: 'MEMBRANE_FILTRATION',
    productName: 'Source-shaped fixture only'
  };

  it('routes by Test-Method and preserves membrane result/tag fields', () => {
    const sourceSamples = [{ location: 'Filling tube-1', tagNo: 'TAG-042', resultDisplay: '7' }];
    const payload = documentPayload(
      'cleaning-validation-rinse-membrane',
      sourceRecord,
      sourceSamples,
      sourceRecord.worksheetNo,
      'membrane-filtration'
    );

    expect(payload.docNo).toBe(sourceRecord.worksheetNo);
    expect(payload.tagNo01).toBe('TAG-042');
    expect(payload.samplingPoint01).toBe('');
    expect(payload.result01).toBe('7');
    expect(payload.resultAvg01).toBeUndefined();
  });

  it('maps a source Result display to the CV Pour average without replicates', () => {
    const payload = documentPayload(
      'cleaning-validation-rinse-pour',
      { ...sourceRecord, testMethod: 'POUR_PLATE' },
      [{ location: 'Filling tube-1', resultDisplay: 'TNTC' }],
      sourceRecord.worksheetNo,
      'pour-plate'
    );

    expect(payload.result101).toBe('');
    expect(payload.result201).toBe('');
    expect(payload.resultAvg01).toBe('TNTC');
  });
});

describe('documentPages', () => {
  it('splits EM at 50 samples and repeats the header on page two', () => {
    const rows = Array.from({ length: 51 }, (_, index) => ({
      samplingPoint: `Room ${index + 1}`,
      tempRoom: index + 1,
      rhRoom: 50 + index
    }));
    const pages = documentPages('em-air', { building: 'Building 10' }, rows, 'AT-26-B10-0001');

    expect(templateSampleCapacity('em-air')).toBe(50);
    expect(pages).toHaveLength(2);
    expect(pages[0].building).toBe('Building 10');
    expect(pages[1].building).toBe('Building 10');
    expect(pages[0].sampleCount).toBe('51');
    expect(pages[1].sampleCount).toBe('51');
    expect(pages[0].roomNo01).toBe('Room 1');
    expect(pages[1].roomNo01).toBe('Room 51');
    expect(pages[1].roomNo50).toBe('');
  });

  it('splits compressed-air at 10 samples without inventing record temperature', () => {
    const rows = Array.from({ length: 11 }, (_, index) => ({
      samplingPoint: `Point ${index + 1}`,
      temp: '',
      rh: ''
    }));
    const pages = documentPages('compressed-air', { temp: '' }, rows, 'AC-26-B10-0001');

    expect(pages).toHaveLength(2);
    expect(pages[1].building).toBe('');
    expect(pages[1].roomNo01).toBe('Point 11');
    expect(pages[1].tempRoom01).toBe('');
    expect(pages[1].temp01).toBe('');
    expect(pages[1].rh01).toBe('');
  });

  it('splits CV rinse at 30 samples and retains page-local results', () => {
    const rows = Array.from({ length: 31 }, (_, index) => ({
      samplingPoint: `Point ${index + 1}`,
      resultAvg: String(index + 1)
    }));
    const pages = documentPages('cleaning-validation-rinse-pour', { sampleMatrix: 'Rinse' }, rows, 'CVR-26-B16-0001');

    expect(pages).toHaveLength(2);
    expect(pages[1].samplingPoint01).toBe('');
    expect(pages[1].resultAvg01).toBe('31');
    expect(pages[1].resultAvg30).toBe('');
  });
});
