// Screenshots for design review: node tests/shots.mjs <outDir> <lang> <device> <name=path>...
import { chromium, devices } from "playwright";
const [out, lang, device, ...targets] = process.argv.slice(2);
const base = process.env.QAYEM_WEB_URL || "http://127.0.0.1:5174";
const browser = await chromium.launch({ headless: true });
const options = device === "mobile" ? { ...devices["iPhone 13"], viewport: { width: 390, height: 844 } } : { viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 };
const context = await browser.newContext(options);
await context.addInitScript((l) => localStorage.setItem("qayem:language", l), lang);
const page = await context.newPage();
page.on("pageerror", (e) => console.log("pageerror:", e.message));
for (const target of targets) {
  const [name, path] = target.split("=");
  await page.goto(base + path.replace(/^=/, ""), { waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  const full = !name.endsWith("-fold");
  await page.screenshot({ path: `${out}/${device}-${lang}-${name}.png`, fullPage: full });
  console.log(name, await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth].join("/")));
}
await browser.close();
