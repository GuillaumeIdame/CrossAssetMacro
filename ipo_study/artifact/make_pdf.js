// Render preview.html to PDF (A4). Run: NODE_PATH=$(npm root -g) node make_pdf.js out.pdf
const { chromium } = require('playwright');
(async () => {
  const out = process.argv[2] || 'IPO_Frenzy_Atlas.pdf';
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 958, height: 1200 }, colorScheme: 'light' });
  await pg.goto('file://' + __dirname + '/preview.html'); await pg.waitForTimeout(1500);
  await pg.evaluate(() => { document.getElementById('det').open = true; });
  await pg.emulateMedia({ media: 'print', colorScheme: 'light' }); await pg.waitForTimeout(500);
  await pg.pdf({ path: out, format: 'A4', printBackground: true, scale: 0.75, margin: { top: '10mm', bottom: '12mm', left: '10mm', right: '10mm' },
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:8px;color:#898781;width:100%;text-align:center;font-family:sans-serif">IPO Frenzy Atlas · data to 13 Nov 2026 · not investment advice · <span class="pageNumber"></span>/<span class="totalPages"></span></div>' });
  await b.close();
})();
