// Renders the brand's raster assets (the share card and the touch icon) from HTML: node tests/render-brand.mjs <og.html> <icon.html>
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
const [og, icon] = process.argv.slice(2);
const out = fileURLToPath(new URL("../public/", import.meta.url));
const browser = await chromium.launch({ headless: true });
for (const [file, width, height, name] of [[og, 1200, 630, "og-default.png"], [icon, 180, 180, "apple-touch-icon.png"]]) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  await page.goto(`file://${file}`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${out}${name}` });
  await page.close();
}
await browser.close();
