/**
 * Isolated Chromium WebGL 2 check for the exported Godot project.
 * Read-only, localhost only, with screenshots to inspect actual game rendering.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
const {chromium} = require('playwright');

(async () => {
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: [
      '--enable-unsafe-swiftshader',
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--disable-dev-shm-usage',
    ],
  });
  try {
    const page = await browser.newPage({
      viewport: {width: 1280, height: 720},
      deviceScaleFactor: 1,
    });
    const errors = [];
    const logs = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('console', m => logs.push(m.type() + ' ' + m.text().slice(0, 300)));
    const response = await page.goto('http://127.0.0.1:8173/index.html', {
      waitUntil: 'domcontentloaded', timeout: 90000,
    });
    assert.equal(response.status(), 200, 'game page HTTP 200');
    await page.waitForFunction(
      () => globalThis.__severancePrototypePhase === 'menu',
      null, {timeout: 90000}
    );
    const canvas = page.locator('canvas');
    await canvas.waitFor({state: 'visible'});
    const rect = await canvas.boundingBox();
    assert(rect && rect.width >= 700 && rect.height >= 400, 'visible Godot canvas');
    await page.screenshot({path: '/tmp/severance-browser-shots/01-menu.png'});
    const before = fs.readFileSync('/tmp/severance-browser-shots/01-menu.png');

    // The rendered 1280x720 Godot title screenshot positions the solo button at y~420, not y~360.
    await page.mouse.click(rect.x + rect.width * 0.5, rect.y + rect.height * 0.583);
    await page.waitForFunction(
      () => globalThis.__severancePrototypePhase === 'solo',
      null, {timeout: 30000}
    );
    await page.waitForTimeout(1500);
    await page.screenshot({path: '/tmp/severance-browser-shots/02-gameplay.png'});
    const after = fs.readFileSync('/tmp/severance-browser-shots/02-gameplay.png');
    assert.notEqual(crypto.createHash('sha256').update(before).digest('hex'),
      crypto.createHash('sha256').update(after).digest('hex'), 'menu transitioned to gameplay');
    await page.keyboard.down('w');
    await page.waitForTimeout(350);
    await page.keyboard.up('w');
    await page.screenshot({path: '/tmp/severance-browser-shots/03-movement.png'});
    fs.writeFileSync('/tmp/severance-browser-shots/console.txt', logs.join('\n') + '\n');
    assert.deepEqual(errors, [], 'no unhandled JavaScript errors');
    console.log('SEVERANCE_CHROMIUM_RENDER_PASS menu, solo, movement, screenshots');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error('SEVERANCE_CHROMIUM_RENDER_FAIL', error);
  process.exitCode = 1;
});
