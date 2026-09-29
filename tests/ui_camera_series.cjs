// Run with Playwright available in NODE_PATH and a local Chrome installation.
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH,
  });
  try {
    const page = await browser.newPage();
    await page.addInitScript(() => {
      window.EventSource = class {
        constructor() { window.testStream = this; }
        close() {}
      };
    });
    await page.goto(pathToFileURL(path.resolve(__dirname, '..', 'chat.html')).href);
    await page.evaluate(() => startStreamingRecommendation('test-session'));
    const variants = [
      { id: 'BG-ADAMO-4KND12X-B', product_url: 'https://example.com/black', price_usd: 1000 },
      { id: 'BG-ADAMO-4KND12X-W', product_url: 'https://example.com/white', price_usd: 1000 },
      { id: 'BG-ADAMO-4KND25X-B', product_url: 'https://example.com/zoom', price_usd: 1200 },
    ];
    await page.evaluate((variants) => {
      for (const variant of variants) {
        window.testStream.onmessage({ data: JSON.stringify({
          type: 'product', tier: 'perfect', product: {
            ...variant, category: 'camera', camera_variants: variants,
          },
        }) });
      }
    }, variants);
    const cards = page.locator('.product-card');
    assert.equal(await cards.count(), 1);
    assert.match(await cards.first().innerText(), /12×, 25×/);
    assert.match(await cards.first().innerText(), /black, white/);
    assert.equal(await cards.first().locator('details a').count(), 3);
    console.log('Camera series UI: 1 card, 3 linked configurations, zoom and colors shown');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
