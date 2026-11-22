import {chromium} from 'playwright-core';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE_URL = 'file://' + path.join(HERE, 'src', 'promo.html');
const OUT = path.join(HERE, 'out', 'frames');

const FPS = 30;
const DURATION = Number(process.env.DURATION || 28);
const W = 1920;
const H = 1080;
const TOTAL = Math.round(FPS * DURATION);

fs.mkdirSync(OUT, {recursive: true});

const browser = await chromium.launch({
  executablePath:
    process.env.CHROME_PATH ||
    '/home/mustp/.cache/ms-playwright/chromium-1255/chrome-linux64/chrome',
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--font-render-hinting=none',
    '--force-color-profile=srgb',
    '--hide-scrollbars',
    '--mute-audio',
    '--disable-lcd-text',
  ],
});

const page = await browser.newPage({
  viewport: {width: W, height: H},
  deviceScaleFactor: 1,
});

page.on('console', (m) => {
  if (m.type() === 'error') console.error('  [page error]', m.text());
});
page.on('pageerror', (e) => console.error('  [page exception]', e.message));

await page.goto(PAGE_URL, {waitUntil: 'load'});
await page.waitForFunction(() => window.__ready === true, {timeout: 30000});
await page.evaluate(() => document.fonts.ready);

// Freeze every animation source: the scene renderer is the only thing that
// changes between frames.
await page.addStyleTag({
  content: `*, *::before, *::after {
    animation-play-state: paused !important;
    animation-delay: -99999s !important;
    transition: none !important;
    caret-color: transparent !important;
  }`,
});

const only = process.env.FRAMES ? process.env.FRAMES.split(',').map(Number) : null;
const list = only || Array.from({length: TOTAL}, (_, i) => i);

const started = Date.now();
for (const f of list) {
  const t = f / FPS;
  await page.evaluate((time) => window.__render(time), t);
  // Let layout/paint settle so the screenshot is the settled frame.
  await page.evaluate(
    () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))),
  );
  const file = path.join(OUT, `f${String(f).padStart(4, '0')}.png`);
  await page.screenshot({path: file, type: 'png'});
  if (f % 30 === 0 || f === list[list.length - 1]) {
    const pct = Math.round(((f + 1) / TOTAL) * 100);
    const el = (Date.now() - started) / 1000;
    console.log(`  frame ${f + 1}/${TOTAL} (${pct}%) ${el.toFixed(1)}s`);
  }
}

await browser.close();
console.log(`rendered ${list.length} frames -> ${OUT}`);
