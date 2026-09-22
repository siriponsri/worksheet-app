/** ANF3 Air — Simple create-only sync (bind this script to air-test) */
const AIR = {
  TZ: 'Asia/Bangkok',
  SOURCE_ID: '1ZImZ3OyfaOQQYcwLlwHFlj9vU6Aqt4fLwv3VMV7sLSo',
  RPP2_ID: '1qhzgsO75jzCwg9h6NnIps1RauMHbyA9MJiwy699vono',
  SOURCES: [
    { name: 'records-Air', type: 'em', prefix: 'AT' },
    { name: 'records-CA Gass', type: 'ca', prefix: 'AC' }
  ]
};

function onOpen(e) { addAirSyncMenu_(); }
function onInstall(e) { onOpen(e); }

function installAirSyncMenu() {
  addAirSyncMenu_();
  SpreadsheetApp.getUi().alert('Air Sync menu installed. Return to air-test and reload once.');
}

function addAirSyncMenu_() {
  SpreadsheetApp.getUi()
    .createMenu('🌬️ Air Sync')
    .addItem('Sync EM-Air → RPP2', 'syncAirEM')
    .addItem('Sync CA-Gas → RPP2', 'syncAirCA')
    .addSeparator()
    .addItem('Sync ทั้งสองระบบ', 'syncAirToRPP2')
    .addToUi();
}

function syncAirEM() { return runAirSync_('em', 'EM-Air'); }
function syncAirCA() { return runAirSync_('ca', 'CA-Gas'); }
function syncAirToRPP2() { return runAirSync_('', 'EM-Air + CA-Gas'); }

function runAirSync_(onlyType, label) {
  const ui = SpreadsheetApp.getUi();
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return ui.alert('มีการ Sync อื่นกำลังทำงานอยู่ กรุณากดลองใหม่');

  try {
    const source = SpreadsheetApp.openById(AIR.SOURCE_ID);
    const rpp2 = SpreadsheetApp.openById(AIR.RPP2_ID);
    const caMaster = (!onlyType || onlyType === 'ca') ? loadCAMaster_(rpp2) : null;
    const report = { created: 0, rows: 0, recovered: 0, warnings: [], errors: [] };

    AIR.SOURCES.forEach(function(cfg) {
      if (onlyType && cfg.type !== onlyType) return;
      mergeAirReport_(report, syncAirSource_(source, rpp2, cfg, caMaster));
    });

    SpreadsheetApp.flush();
    showAirReport_(ui, report, label);
    return report;
  } catch (e) {
    ui.alert('Air Sync — ERROR', String(e.message || e), ui.ButtonSet.OK);
    throw e;
  } finally {
    lock.releaseLock();
  }
}

function syncAirSource_(sourceSS, rpp2SS, cfg, caMaster) {
  const out = { created: 0, rows: 0, recovered: 0, warnings: [], errors: [] };
  const sh = sourceSS.getSheetByName(cfg.name);
  if (!sh) throw new Error('ไม่พบ source tab: ' + cfg.name);
  if (sh.getLastRow() < 2) return out;

  const data = sh.getDataRange().getValues();
  const c = sourceCols_(data[0], cfg);
  const groups = {};

  data.slice(1).forEach(function(row, i) {
    if (!isTrue_(row[c.worksheetCreate]) || !isBlank_(row[c.syncStatus])) return;

    const date = dateKey_(row[c.samplingDate]);
    const building = text_(row[c.building]) || 'Unknown';

    // APPROVED: combine all EM Methods in one worksheet for now.
    // FUTURE: to split Settle Plate / Active Air, add Method to this group key.
    const key = date + '|' + building.toUpperCase();

    if (!groups[key]) groups[key] = [];
    groups[key].push({ row: row, rowNo: i + 2, date: date, building: building });
  });

  Object.keys(groups).forEach(function(key) {
    try {
      syncAirGroup_(sh, rpp2SS, cfg, c, groups[key], caMaster, out);
    } catch (e) {
      out.errors.push(cfg.name + ' / ' + key + ': ' + String(e.message || e));
    }
  });

  return out;
}

function syncAirGroup_(sourceSheet, rpp2SS, cfg, c, items, caMaster, out) {
  const first = items[0].row;
  const building = items[0].building;
  const route = route_(cfg.type, building);
  const target = rpp2SS.getSheetByName(route.tab);
  if (!target) throw new Error('ไม่พบ target tab: ' + route.tab);

  let recordStatus = 'Routine';
  if (cfg.type === 'em') {
    const statuses = unique_(items.map(function(x) { return x.row[c.recordStatus]; }));
    recordStatus = text_(first[c.recordStatus]) || 'Routine';
    if (statuses.length > 1) {
      out.warnings.push(
        items[0].date + ' / ' + building +
        ' มี Group [' + statuses.join(', ') +
        '] → RPP2.recordStatus ใช้ค่าจากแถวแรก: ' + recordStatus
      );
    }
  }

  // Existing worksheetNo = recovery/legacy. Search all shards before creating anything.
  const existingNos = unique_(items.map(function(x) { return x.row[c.worksheetNo]; }));
  if (existingNos.length > 1) throw new Error('พบ worksheetNo มากกว่า 1 ค่าในกลุ่มเดียวกัน');

  let worksheetNo = existingNos[0] || '';

  if (worksheetNo) {
    const found = findWorksheetInRPP2_(rpp2SS, cfg.type, worksheetNo);
    if (found) {
      markSynced_(sourceSheet, items, c.syncStatus);
      out.recovered++;
      out.rows += items.length;
      if (found.getName() !== route.tab) {
        out.warnings.push(
          worksheetNo + ' มีอยู่แล้วใน ' + found.getName() +
          ' → mark synced เท่านั้น ไม่สร้างซ้ำใน ' + route.tab
        );
      }
      return;
    }

    if (!validNo_(worksheetNo, cfg.prefix, route.segment)) {
      throw new Error(
        'พบ worksheetNo เดิม ' + worksheetNo +
        ' แต่ค้นไม่พบใน RPP2 และเลขไม่ตรง format ใหม่ของ ' + route.tab +
        ' (หากต้องการสร้างใหม่ ให้ล้าง worksheetNo ของกลุ่มนี้ก่อนแล้ว Sync อีกครั้ง)'
      );
    }
  } else {
    worksheetNo = nextNo_(target, sourceSheet, c.worksheetNo, cfg.prefix, route.segment);
    items.forEach(function(x) {
      sourceSheet.getRange(x.rowNo, c.worksheetNo + 1).setValue(worksheetNo);
    });
  }

  // Interrupted-run recovery: number was reserved and target append already succeeded.
  if (hasWorksheet_(target, worksheetNo)) {
    markSynced_(sourceSheet, items, c.syncStatus);
    out.recovered++;
    out.rows += items.length;
    return;
  }

  const samples = cfg.type === 'em'
    ? buildEMSamples_(items, c)
    : buildCASamples_(items, c, caMaster, out);

  appendByHeader_(
    target,
    buildRecord_(cfg.type, first, c, building, recordStatus, worksheetNo, samples)
  );

  markSynced_(sourceSheet, items, c.syncStatus);
  out.created++;
  out.rows += items.length;
}

function route_(type, building) {
  const b = buildingCode_(building);
  const segment = (b === 'B10' || b === 'B12' || b === 'B16') ? b : 'OT';

  if (type === 'em') return { tab: 'records_em_' + segment, segment: segment };
  if (type === 'ca') return { tab: 'records_ca_' + segment, segment: segment };
  throw new Error('Unsupported Air type: ' + type);
}

function nextNo_(target, source, sourceNoCol, prefix, segment) {
  const yy = Utilities.formatDate(new Date(), AIR.TZ, 'yy');
  const re = new RegExp('^' + prefix + '-' + yy + '-' + segment + '-(\\d{4})$');
  let max = 0;

  if (target.getLastRow() > 1) {
    target.getRange(2, 1, target.getLastRow() - 1, 1).getValues().forEach(function(r) {
      const m = text_(r[0]).toUpperCase().match(re);
      if (m) max = Math.max(max, Number(m[1]));
    });
  }

  // Include numbers reserved in air-test after a failed/interrupted run.
  if (source.getLastRow() > 1) {
    source.getRange(2, sourceNoCol + 1, source.getLastRow() - 1, 1).getValues().forEach(function(r) {
      const m = text_(r[0]).toUpperCase().match(re);
      if (m) max = Math.max(max, Number(m[1]));
    });
  }

  return prefix + '-' + yy + '-' + segment + '-' + pad4_(max + 1);
}

function validNo_(no, prefix, segment) {
  const yy = Utilities.formatDate(new Date(), AIR.TZ, 'yy');
  return new RegExp('^' + prefix + '-' + yy + '-' + segment + '-\\d{4}$')
    .test(text_(no).toUpperCase());
}

function findWorksheetInRPP2_(rpp2SS, type, worksheetNo) {
  const tabs = type === 'em'
    ? ['records_em_B10', 'records_em_B12', 'records_em_B16', 'records_em_OT']
    : ['records_ca_B10', 'records_ca_B12', 'records_ca_B16', 'records_ca_OT'];

  for (let i = 0; i < tabs.length; i++) {
    const sh = rpp2SS.getSheetByName(tabs[i]);
    if (sh && hasWorksheet_(sh, worksheetNo)) return sh;
  }
  return null;
}

function hasWorksheet_(sheet, no) {
  if (!sheet || sheet.getLastRow() < 2) return false;
  return Boolean(
    sheet.getRange(2, 1, sheet.getLastRow() - 1, 1)
      .createTextFinder(String(no)).matchEntireCell(true).findNext()
  );
}

function buildEMSamples_(items, c) {
  return items.map(function(x, i) {
    const row = x.row;
    const roomNo = text_(row[c.roomNo]);
    return {
      index: i + 1,
      samplingPoint: roomNo,
      noLocation: roomNo,
      location: text_(row[c.roomName]),
      samplingMode: normalizeSamplingMode_(row[c.method]),
      floor: text_(row[c.floor]),
      grade: text_(row[c.grade]),
      tempRoom: naIfBlank_(row[c.temp]),
      rhRoom: naIfBlank_(row[c.rh]),
      timeIn: naIfBlank_(formatTime_(row[c.timeIn])),
      timeOut: naIfBlank_(formatTime_(row[c.timeOut])),
      occurResult: '', // RPP2/lab owns result
      remark: naIfBlank_(row[c.remark])
    };
  });
}

function buildCASamples_(items, c, master, out) {
  const missing = [];

  const samples = items.map(function(x, i) {
    const row = x.row;
    const roomNo = text_(row[c.roomNo]);
    const tag = text_(row[c.tag]);
    const m = lookupCAMaster_(master, roomNo, tag);

    if (!m) missing.push(tag || roomNo || ('row ' + x.rowNo));

    return {
      index: i + 1,
      samplingPoint: roomNo,
      noLocation: roomNo,
      location: text_(row[c.roomName]),
      samplingTag: tag,
      grade: m ? text_(m.grade) : '',
      airType: m ? text_(m.airType) : '',
      temp: naIfBlank_(row[c.temp]),
      rh: naIfBlank_(row[c.rh]),
      occResult: '', // RPP2/lab owns result
      remark: text_(row[c.remark])
    };
  });

  if (missing.length) {
    out.warnings.push(
      items[0].date + ' / ' + items[0].building +
      ' CA ไม่พบ master ใน database_ca สำหรับ: ' + missing.join(', ') +
      ' → grade/airType ถูกเว้นว่าง'
    );
  }

  return samples;
}

function buildRecord_(type, first, c, building, recordStatus, worksheetNo, samples) {
  const now = new Date().toISOString();
  const samplingDate = dateKey_(first[c.samplingDate]);
  const record = {
    worksheetNo: worksheetNo,
    recordStatus: type === 'em' ? recordStatus : 'Routine',
    building: building,
    samplingDate: samplingDate,
    performedDate: samplingDate,
    temp: text_(first[c.temp]),
    incNo: '',
    mfgMedia: formatDateText_(first[c.mfgDate]),
    expMedia: formatDateText_(first[c.expDate]),
    determinedDate: '',
    concludedDate: '',
    approvedDate: '',
    docNo: worksheetNo,
    samplesJson: JSON.stringify(samples),
    createdAt: now,
    updatedAt: now,
    createdBy: 'air-test-sync' // no Session.getActiveUser() permission needed
  };

  if (type === 'em') record.lotMedia = text_(first[c.lotTSA]);
  if (type === 'ca') {
    record.lotTSA = text_(first[c.lotTSA]);
    record.lotMedia = text_(first[c.lotTSA]);
    record.lotOther = '';
  }
  return record;
}

function appendByHeader_(sheet, record) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  ['worksheetNo', 'recordStatus', 'building', 'samplingDate', 'performedDate', 'docNo', 'samplesJson']
    .forEach(function(h) {
      if (headers.indexOf(h) < 0) throw new Error(sheet.getName() + ' ไม่มีคอลัมน์ ' + h);
    });

  const row = headers.map(function(h) {
    return Object.prototype.hasOwnProperty.call(record, h) ? record[h] : '';
  });

  sheet.getRange(sheet.getLastRow() + 1, 1, 1, row.length).setValues([row]);
}

/**
 * CA master comes directly from RPP2/database_ca.
 * Priority: source Tag -> database_ca.samplingTag, then roomNo fallbacks.
 */
function loadCAMaster_(rpp2SS) {
  const sh = rpp2SS.getSheetByName('database_ca');
  if (!sh) throw new Error('ไม่พบ RPP2 tab: database_ca');

  const data = sh.getDataRange().getValues();
  const master = { byTag: {}, byLabel: {}, byLocation: {} };
  if (data.length < 2) return master;

  const h = data[0];
  const c = {
    label: findCol_(h, ['samplingLabel']),
    location: findCol_(h, ['noLocation']),
    tag: findCol_(h, ['samplingTag']),
    grade: findCol_(h, ['grade']),
    airType: findCol_(h, ['airType'])
  };

  data.slice(1).forEach(function(row) {
    const item = { grade: row[c.grade], airType: row[c.airType] };
    const tag = text_(row[c.tag]).toUpperCase();
    const label = text_(row[c.label]).toUpperCase();
    const location = text_(row[c.location]).toUpperCase();

    if (tag) master.byTag[tag] = item;
    if (label) master.byLabel[label] = item;
    // noLocation may be duplicated; keep first as fallback.
    if (location && !master.byLocation[location]) master.byLocation[location] = item;
  });

  return master;
}

function lookupCAMaster_(master, roomNo, tag) {
  if (!master) return null;
  const t = text_(tag).toUpperCase();
  const r = text_(roomNo).toUpperCase();
  return (t && master.byTag[t]) ||
         (r && master.byLabel[r]) ||
         (r && master.byLocation[r]) ||
         null;
}

function sourceCols_(headers, cfg) {
  const c = {
    samplingDate: findCol_(headers, ['Sampling Date', 'SamplingDate', 'samplingDate']),
    worksheetNo: findCol_(headers, ['worksheetNo', 'worksheet No.']),
    worksheetCreate: findCol_(headers, ['worksheetCreate']),
    syncStatus: findCol_(headers, ['syncStatus', 'anf3SyncStatus']),
    building: findCol_(headers, ['building']),
    roomNo: findCol_(headers, ['roomNo']),
    roomName: findCol_(headers, ['roomName']),
    temp: findCol_(headers, ['temp']),
    rh: findCol_(headers, ['%rh', 'rh']),
    timeIn: findCol_(headers, ['timeIn']),
    timeOut: findCol_(headers, ['timeOut']),
    lotTSA: findCol_(headers, ['lotTSA']),
    mfgDate: findCol_(headers, ['mfgDate']),
    expDate: findCol_(headers, ['expDate']),
    remark: findCol_(headers, ['remark'])
  };

  if (cfg.type === 'em') {
    c.recordStatus = findCol_(headers, ['Group', 'recordStatus']);
    c.method = findCol_(headers, ['Method']); // kept for future Method split
    c.floor = findCol_(headers, ['floor']);
    c.grade = findCol_(headers, ['Class', 'grade']);
  } else {
    c.tag = findCol_(headers, ['Tag', 'samplingTag']);
  }
  return c;
}

function findCol_(headers, aliases) {
  for (let a = 0; a < aliases.length; a++) {
    const wanted = norm_(aliases[a]);
    for (let i = 0; i < headers.length; i++) {
      if (norm_(headers[i]) === wanted) return i;
    }
  }
  throw new Error('ไม่พบคอลัมน์: ' + aliases.join(' / '));
}

function markSynced_(sheet, items, syncStatusCol) {
  items.forEach(function(x) {
    sheet.getRange(x.rowNo, syncStatusCol + 1).setValue('synced');
  });
}

function buildingCode_(value) {
  const s = text_(value).toUpperCase().replace(/[ _-]+/g, '');
  const m = s.match(/^(?:BUILDING|BLDG|BLD|B)?(10|12|16)$/);
  return m ? 'B' + m[1] : 'OT';
}

function dateKey_(value) {
  if (!value) return 'NO_DATE';
  if (Object.prototype.toString.call(value) === '[object Date]' && !isNaN(value.getTime())) {
    return Utilities.formatDate(value, AIR.TZ, 'yyyy-MM-dd');
  }
  const d = new Date(value);
  return !isNaN(d.getTime()) ? Utilities.formatDate(d, AIR.TZ, 'yyyy-MM-dd') : (text_(value) || 'NO_DATE');
}

function formatDateText_(value) {
  if (isBlank_(value)) return '';
  if (Object.prototype.toString.call(value) === '[object Date]' && !isNaN(value.getTime())) {
    return Utilities.formatDate(value, AIR.TZ, 'yyyy-MM-dd');
  }
  const d = new Date(value);
  return !isNaN(d.getTime()) ? Utilities.formatDate(d, AIR.TZ, 'yyyy-MM-dd') : text_(value);
}

function formatTime_(value) {
  if (isBlank_(value)) return '';
  if (Object.prototype.toString.call(value) === '[object Date]' && !isNaN(value.getTime())) {
    return Utilities.formatDate(value, AIR.TZ, 'HH:mm');
  }
  return text_(value);
}

function naIfBlank_(value) { const v = text_(value); return v === '' ? 'N/A' : v; }
// The source workbook's Method values are the only authoritative mode labels.
// Unknown/blank values remain blank so historical records are not fabricated.
function normalizeSamplingMode_(value) {
  const token = text_(value).toLowerCase().replace(/[\s_-]+/g, '');
  if (token === 'settleplate' || token === 'passive') return 'passive';
  if (token === 'activeair' || token === 'active') return 'active';
  return '';
}
function norm_(value) { return String(value || '').toLowerCase().replace(/[\s._%-]+/g, ''); }
function text_(value) { return value === null || value === undefined ? '' : String(value).trim(); }
function isBlank_(value) { return value === '' || value === null || value === undefined; }
function isTrue_(value) { return value === true || text_(value).toUpperCase() === 'TRUE'; }

function unique_(values) {
  const seen = {};
  const out = [];
  values.forEach(function(value) {
    const v = text_(value);
    if (v && !seen[v]) { seen[v] = true; out.push(v); }
  });
  return out;
}

function pad4_(n) {
  let s = String(n);
  while (s.length < 4) s = '0' + s;
  return s;
}

function mergeAirReport_(a, b) {
  a.created += b.created;
  a.rows += b.rows;
  a.recovered += b.recovered;
  Array.prototype.push.apply(a.warnings, b.warnings);
  Array.prototype.push.apply(a.errors, b.errors);
}

function showAirReport_(ui, r, label) {
  let msg =
    'สร้าง worksheet ใหม่: ' + r.created + '\n' +
    'แถวที่ sync สำเร็จ: ' + r.rows + '\n' +
    'Recovery (ไม่สร้างซ้ำ): ' + r.recovered + '\n' +
    'Errors: ' + r.errors.length;

  if (r.warnings.length) msg += '\n\nWarnings:\n- ' + r.warnings.join('\n- ');
  if (r.errors.length) msg += '\n\nErrors:\n- ' + r.errors.join('\n- ');
  if (!r.created && !r.rows && !r.errors.length) {
    msg += '\n\nไม่พบแถวที่ worksheetCreate = TRUE และ syncStatus ว่าง';
  }

  ui.alert('Air Sync → RPP2' + (label ? ' (' + label + ')' : ''), msg, ui.ButtonSet.OK);
}
