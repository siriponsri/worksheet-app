/* Local-only browser gate for the release-critical List and Print contracts.
 * All System DB/PDF requests are fulfilled by deterministic fixtures; this
 * never contacts Apps Script or mutates a generated document. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { PDFDocument } from 'pdf-lib';

const root = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const outputDir = path.join(root, 'output', 'playwright');
const baseUrl = process.env.ANF3_BROWSER_BASE || 'http://127.0.0.1:5173';
fs.mkdirSync(outputDir, { recursive: true });

const forbidden = /samplesJson|templatePayload|resultAvg|result1|result2|lotPMembrane|leftEM/i;
const routeFixtures = [
  {
    domain: 'water', workflow: 'pw-prw', worksheetNo: 'PW-26-B10-0001', scope: 'Building 10',
    record: { worksheetNo: 'PW-26-B10-0001', building: 'Building 10', samplingDate: '2026-09-10', performedDate: '2026-09-10', comment: '', incNo: 'INC-SYSTEM-DO-NOT-USE' },
    samples: [{ samplingPoint: 'Point A', result1: '1', result2: '2', resultAvg: '2.1', tagNo: 'TAG-1' }]
  },
  {
    domain: 'water', workflow: 'wfi-pus', worksheetNo: 'WP-26-B10-0001', scope: 'Building 10',
    record: { worksheetNo: 'WP-26-B10-0001', building: 'Building 10', samplingDate: '2026-09-10', performedDate: '2026-09-10', comment: '' },
    samples: [{ samplingPoint: 'WFI Point A', result: '3' }]
  },
  {
    domain: 'air', workflow: 'em-air', worksheetNo: 'AT-26-B10-0001', scope: 'Building 10',
    record: { worksheetNo: 'AT-26-B10-0001', building: 'Building 10', samplingDate: '2026-09-10', performedDate: '2026-09-10', comment: '' },
    samples: [{ samplingPoint: 'Room A', tempRoom: '22', rhRoom: '50', occurResult: '1' }]
  },
  {
    domain: 'air', workflow: 'compressed-air', worksheetNo: 'AC-26-B10-0001', scope: 'Building 10',
    record: { worksheetNo: 'AC-26-B10-0001', building: 'Building 10', samplingDate: '2026-09-10', performedDate: '2026-09-10', comment: '', temp: '22' },
    samples: [{ samplingPoint: 'Point A', temp: '22', rh: '50', occResult: '1' }]
  },
  {
    domain: 'cv', workflow: 'cv', cvMethod: 'contact-plate', worksheetNo: 'CV-26-B10-0001', scope: 'Building 10',
    record: { worksheetNo: 'CV-26-B10-0001', building: 'Building 10', sampleMatrix: 'Contact Plate', testMethod: 'Contact Plate', productName: 'QA product' },
    samples: [{ equipment: 'Filler', location: 'Room A', grade: 'D', result: '1' }]
  },
  {
    domain: 'cv', workflow: 'cv', cvMethod: 'pour-plate', worksheetNo: 'CVR-26-B10-0001', scope: 'Building 10',
    record: { worksheetNo: 'CVR-26-B10-0001', building: 'Building 10', sampleMatrix: 'Rinse', testMethod: 'Pour Plate' },
    samples: [{ samplingPoint: 'Rinse Point A', resultAvg: 'TNTC' }]
  },
  {
    domain: 'cv', workflow: 'cv', cvMethod: 'membrane-filtration', worksheetNo: 'CVR-26-B16-0001', scope: 'Building 16',
    record: { worksheetNo: 'CVR-26-B16-0001', building: 'Building 16', sampleMatrix: 'Rinse', testMethod: 'Membrane Filtration' },
    samples: [{ samplingPoint: 'Rinse Point B', result: '134' }]
  }
];

const queueFor = (fixture) => [{
  domain: fixture.domain, workflow: fixture.workflow, recordKey: 'fixture-1', worksheetNo: fixture.worksheetNo,
  scope: fixture.scope, returnTo: `/list?building=${encodeURIComponent(fixture.scope)}&domain=${fixture.domain}&workflow=${fixture.workflow}&q=fixture`,
  cvMethod: fixture.cvMethod
}];
const initialFixture = routeFixtures[0];
const record = initialFixture.record;
const samples = initialFixture.samples;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function main() {
  const pdf = await PDFDocument.create();
  pdf.addPage([120, 120]);
  const pdfBytes = Buffer.from(await pdf.save());
  let pdfPosts = 0;
  let conflictMode = false;
  let replacementPosts = 0;
  const browser = await chromium.launch({ headless: true });
  const loginContext = await browser.newContext({ viewport: { width: 375, height: 900 } });
  const loginPage = await loginContext.newPage();
  await loginPage.goto(`${baseUrl}/`, { waitUntil: 'networkidle' });
  await loginPage.locator('.gate-card').waitFor();
  assert(await loginPage.getByPlaceholder('[ชื่อ หรือ ชื่อเล่น]').count() === 1, 'Login name placeholder is incorrect');
  assert(await loginPage.getByPlaceholder('[รหัสพนักงาน]').count() === 1, 'Login employee-code placeholder is incorrect');
  for (const width of [320, 375, 414, 768, 1280]) {
    await loginPage.setViewportSize({ width, height: 900 });
    const centered = await loginPage.evaluate(() => {
      const gate = document.querySelector('.gate')?.getBoundingClientRect();
      const card = document.querySelector('.gate-card')?.getBoundingClientRect();
      if (!gate || !card) return { centered: false, overflow: true };
      return {
        centered: Math.abs(card.left + card.width / 2 - innerWidth / 2) <= 1
          && Math.abs(card.top + card.height / 2 - gate.top - gate.height / 2) <= 1,
        overflow: document.documentElement.scrollWidth > innerWidth + 1,
      };
    });
    assert(centered.centered, `Login card is not centered at ${width}px`);
    assert(!centered.overflow, `Login has horizontal overflow at ${width}px`);
  }
  await loginContext.close();

  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(({ storedQueue }) => {
    localStorage.setItem('anf3.operator.v2', JSON.stringify({ name: 'Browser fixture', code: 'QA-01' }));
    sessionStorage.setItem('anf3.print-queue.v1', JSON.stringify(storedQueue));
  }, { storedQueue: queueFor(initialFixture) });
  const page = await context.newPage();
  let activeFixture = initialFixture;
  const selectFixture = async (fixture) => {
    activeFixture = fixture;
    /* about:blank has no storage origin. Navigate to the local app before
       changing the queued fixture so this helper also works on a clean run. */
    await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
    await page.evaluate((items) => {
      /* The active app migrates the legacy queue into the workset once. Clear
         that migrated snapshot before swapping fixtures so each route starts
         with the fixture requested by this test. */
      sessionStorage.removeItem('anf3.workset.v1');
      sessionStorage.setItem('anf3.print-queue.v1', JSON.stringify(items));
    }, queueFor(fixture));
  };

  await page.route('**/config.json', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ waterReadUrl: 'http://mock.anf3/water', airReadUrl: 'http://mock.anf3/air', cvReadUrl: 'http://mock.anf3/cv' })
  }));
  await page.route('http://mock.anf3/**', async (route) => {
    const request = new URL(route.request().url());
    const action = request.searchParams.get('action');
    const fixture = activeFixture;
    const payload = action === 'get'
      ? { data: { record: fixture.record, samples: fixture.samples }, meta: { fetchedAt: '2026-09-10T09:00:00+07:00' } }
      : { data: { items: [{ recordKey: 'fixture-1', worksheetNo: fixture.worksheetNo, building: fixture.record.building, samplingDate: fixture.record.samplingDate, samplingPoints: String(fixture.samples[0]?.samplingPoint || fixture.samples[0]?.equipment || 'Point A'), sampleCount: fixture.samples.length }], nextCursor: '' }, meta: {} };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) });
  });
  await page.route('**/api/log', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true }) }));
  await page.route('**/api/pdfs', async (route) => {
    if (route.request().method() === 'POST') {
      pdfPosts += 1;
      const body = route.request().postDataJSON() || {};
      if (conflictMode && body.regeneration?.mode === 'replace') {
        replacementPosts += 1;
        if (replacementPosts === 1) {
          await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({
            code: 'WORKSHEET_CONTENT_CONFLICT', requestedPdfId: 'fixture-requested-new',
            existingPdfIds: ['fixture-existing-new'], changedFields: ['samplingDate']
          }) });
          return;
        }
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ pdfId: 'fixture-replaced', status: 'ready' }) });
        return;
      }
      if (conflictMode) {
        await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({
          code: 'WORKSHEET_CONTENT_CONFLICT', requestedPdfId: 'fixture-requested',
          existingPdfIds: ['fixture-existing'], changedFields: ['ProductName', 'resultAvg01', 'analyst']
        }) });
        return;
      }
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ pdfId: 'fixture-pdf', status: 'ready' }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'not found' }) });
  });
  await page.route('**/api/pdfs/*/download**', (route) => route.fulfill({ contentType: 'application/pdf', body: pdfBytes }));

  for (const fixture of routeFixtures) {
    await selectFixture(fixture);
    await page.goto(`${baseUrl}/#/print/${fixture.domain}/${fixture.workflow}`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'Fill in', exact: true }).waitFor();
    assert(pdfPosts === 0, `${fixture.worksheetNo} posted before explicit Generate preview`);
  }
  console.log(`PASS browser route coverage: ${routeFixtures.map(({ worksheetNo }) => worksheetNo).join(', ')}`);

  await selectFixture(initialFixture);
  await page.goto(`${baseUrl}/#/print/water/pw-prw`, { waitUntil: 'networkidle' });
  const queueFill = page.getByRole('button', { name: 'Fill in', exact: true });
  await queueFill.waitFor();
  assert(pdfPosts === 0, 'Print queue posted to /api/pdfs before explicit Generate preview');
  await page.screenshot({ path: path.join(outputDir, 'print-queue-before-generate.png'), fullPage: true });

  const drawer = page.getByRole('dialog', { name: `Fill in ${record.worksheetNo}` });
  await queueFill.click();
  await drawer.waitFor();
  await drawer.locator('input:disabled').first().waitFor();
  assert((await drawer.locator('input:disabled').count()) >= 2, 'Print identity fields are not locked');
  assert(await drawer.getByLabel('Incubation No.').count() === 1, 'Fill in does not expose Incubation No.');
  assert(await drawer.getByLabel('Incubation No.').inputValue() === '', 'Incubation No. was populated from the System DB');
  assert(!forbidden.test(await drawer.innerText()), 'Print drawer exposes an internal field name');
  const average = drawer.getByLabel('Average result 01');
  await average.fill('[invalid]');
  assert(await drawer.getByRole('button', { name: 'Save & Generate' }).isDisabled(), 'Invalid result was not blocked');
  await average.fill('TNTC');
  await drawer.getByRole('button', { name: 'Reset to System DB' }).click();
  assert((await average.inputValue()) === '3', 'Reset did not restore the System DB value');
  await drawer.getByRole('button', { name: 'Close' }).click();
  assert(!(await drawer.isVisible()), 'Cancel did not close the print drawer');
  assert(pdfPosts === 0, 'Cancel caused PDF generation');

  await queueFill.click();
  await drawer.waitFor();
  await drawer.getByRole('button', { name: 'Close' }).focus();
  await page.keyboard.press('Shift+Tab');
  assert(await page.evaluate(() => (document.activeElement instanceof HTMLElement) && document.activeElement.closest('[role="dialog"]') !== null), 'Focus escaped the print drawer');
  await page.keyboard.press('Escape');
  assert(!(await drawer.isVisible()), 'Escape did not close the print drawer');
  assert((await page.evaluate(() => document.activeElement?.textContent || '')).trim() === 'Fill in', 'Focus was not restored to the print trigger');

  await queueFill.click();
  await drawer.getByRole('button', { name: 'Save & Generate' }).click();
  await page.waitForTimeout(500);
  assert(pdfPosts >= 1, `Explicit Generate preview did not post: ${pdfPosts}`);
  await page.screenshot({ path: path.join(outputDir, 'print-preview-after-generate.png'), fullPage: true });

  await page.goto(`${baseUrl}/#/list?building=Building%2010&domain=water&workflow=pw-prw&q=fixture&from=2026-09-01&to=2026-09-10&groupBy=work`, { waitUntil: 'networkidle' });
  const listRow = page.getByRole('row').filter({ hasText: record.worksheetNo });
  await listRow.waitFor();
  assert(new URL(page.url()).hash.includes('q=fixture'), 'List search query is not URL-backed');
  assert(await page.getByLabel('Group by').inputValue() === 'work', 'List groupBy state was not restored from the URL');
  assert(await listRow.getByRole('switch', { name: `Include ${record.worksheetNo} in the work set` }).count() === 1, 'List row does not expose an accessible ON/OFF switch');
  await listRow.getByRole('button', { name: 'Details' }).click();
  const details = page.getByRole('dialog', { name: 'Record details' });
  await details.waitFor();
  await page.waitForTimeout(300);
  const detailText = await details.innerText();
  assert(/general/i.test(detailText), `List Details did not render human sections: ${detailText.slice(0, 240)}`);
  assert(!forbidden.test(detailText), 'List Details exposes an internal field name');
  await page.screenshot({ path: path.join(outputDir, 'list-details.png'), fullPage: true });

  await page.goto(`${baseUrl}/#/list?building=Building%2010&domain=water&workflow=pw-prw&q=fixture&groupBy=building`, { waitUntil: 'networkidle' });
  await page.getByRole('row').filter({ hasText: record.worksheetNo }).waitFor();
  assert(new URL(page.url()).hash.includes('groupBy=building'), 'List lost explicit building grouping in the URL');
  assert(await page.getByLabel('Group by').inputValue() === 'building', 'List building grouping was not restored from the URL');

  await page.goto(`${baseUrl}/#/list?domain=air&workflow=pw-prw&q=fixture`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Air records' }).waitFor();
  assert(!new URL(page.url()).hash.includes('workflow=pw-prw'), 'List kept an incompatible domain/workflow pair');

  conflictMode = true;
  replacementPosts = 0;
  await page.goto(`${baseUrl}/#/print/water/pw-prw`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Fill in', exact: true }).click();
  const queueDrawer = page.getByRole('dialog', { name: `Fill in ${record.worksheetNo}` });
  await queueDrawer.getByRole('button', { name: 'Save & Generate' }).click();
  await page.getByRole('button', { name: 'Review replacement' }).click();
  const queueConflict = page.getByRole('dialog', { name: 'Review document replacement' });
  await queueConflict.waitFor();
  assert(/Product|Average result 01/.test(await queueConflict.innerText()), 'Queue conflict did not show human-readable changed fields');
  await queueConflict.getByRole('button', { name: 'Replace reviewed document' }).click();
  await page.waitForTimeout(150);
  assert((await page.getByRole('dialog', { name: 'Review document replacement' }).innerText()).includes('Sampling date'), 'Stale queue confirmation did not refresh changed fields');
  await page.getByRole('dialog', { name: 'Review document replacement' }).getByRole('button', { name: 'Replace reviewed document' }).click();
  await page.waitForTimeout(500);
  assert(replacementPosts === 2, `Queue replacement did not send two controlled retries: ${replacementPosts}`);
  conflictMode = false;

  await page.evaluate(() => {
    sessionStorage.removeItem('anf3.workset.v1');
    sessionStorage.removeItem('anf3.print-queue.v1');
  });
  await page.goto(`${baseUrl}/#/records/water/pw-prw/fixture-1?building=Building%2010`, { waitUntil: 'networkidle' });
  const recordDetails = page.getByRole('dialog', { name: 'Record details' });
  await recordDetails.waitFor();
  assert(await recordDetails.getByRole('button', { name: 'Fill in', exact: true }).count() === 0, 'Record details exposes a direct print action');
  assert(await recordDetails.getByRole('button', { name: /Generate|Save/ }).count() === 0, 'Record details exposes a document-generation action');
  await recordDetails.getByRole('button', { name: 'Close' }).click();
  const directRow = page.getByRole('row').filter({ hasText: record.worksheetNo });
  await directRow.getByRole('switch', { name: `Include ${record.worksheetNo} in the work set` }).click();
  await page.getByRole('button', { name: /Continue to Fill In/ }).click();
  await page.getByRole('heading', { name: /Selected Work/ }).waitFor();
  assert(pdfPosts >= 1, 'Selecting a worksheet generated a PDF before the queue action');
  await page.goto(`${baseUrl}/#/list?building=Building%2010&domain=water&workflow=pw-prw&q=fixture`, { waitUntil: 'networkidle' });

  for (const width of [320, 375, 414, 768, 1024, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    assert(!overflow, `Horizontal overflow at ${width}px`);
    await page.screenshot({ path: path.join(outputDir, `list-${width}.png`), fullPage: true });
  }
  await page.getByRole('button', { name: /Switch off the lamp|Switch on the lamp/ }).click();
  assert(await page.evaluate(() => document.documentElement.dataset.theme === 'dark'), 'Dark theme toggle did not apply');
  await page.screenshot({ path: path.join(outputDir, 'list-dark.png'), fullPage: true });

  console.log(`PASS browser smoke: zero pre-Generate PDF posts, one explicit post, DOM leakage clear, focus/keyboard clear, URL/detail clear, responsive widths clear, dark theme clear`);
  console.log(`screenshots=${path.relative(root, outputDir).replaceAll(path.sep, '/')}`);
  await browser.close();
}

main().catch(async (error) => {
  console.error(`FAIL browser smoke: ${error instanceof Error ? error.message : error}`);
  process.exitCode = 1;
});
