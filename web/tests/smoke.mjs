// End-to-end smoke test against the real, read-only catalog.
// Start the API first (./scripts/serve-web.sh), then: QAYEM_WEB_URL=http://127.0.0.1:8000 npm run test:e2e
// Every page is opened in Arabic and English, on desktop and on a phone, and checked for
// runtime errors, failed API calls, horizontal overflow, untranslated copy and small tap targets.
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, devices } from "playwright";

const baseURL = process.env.QAYEM_WEB_URL || "http://127.0.0.1:5174";
const artifacts = fileURLToPath(new URL("../test-results/", import.meta.url));
await mkdir(artifacts, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || (existsSync("/usr/bin/google-chrome") ? "/usr/bin/google-chrome" : undefined),
  headless: true,
  args: ["--no-sandbox"],
});

const api = async (path) => {
  const response = await fetch(`${baseURL}/api${path}`);
  assert.ok(response.ok, `${path} → ${response.status}`);
  return response.json();
};
const overview = await api("/overview");
const unit = (await api("/units?sort=value&page_size=1")).items[0];
const plan = (await api("/units?terms=plan&grade=A&page_size=1")).items[0];
const compound = (await api("/compounds?page_size=1")).items[0];
const developer = (await api("/developers?sort=premium_desc&page_size=1")).items[0];
const second = (await api("/compounds?page_size=2&page=1")).items[1];
const catalog = await api("/catalog");
const launched = (await api("/compounds?page_size=100")).items.find((c) => c.launch);
const verified = (await api("/units?source=aqarexit&terms=plan&page_size=1")).items[0];
// Data never needs translating: entity names, source names, source-quoted evidence.
const dataNames = [
  ...catalog.compounds.map((c) => c.name),
  ...catalog.developers.map((d) => d.name),
  ...catalog.districts.map((d) => d.name),
  ...overview.sources.map((s) => s.name),
]
  .filter((name) => /[A-Za-z]/.test(name))
  .sort((a, b) => b.length - a.length);
assert.ok(overview.valued_count > 0 && unit && plan && compound && developer, "catalog has valued units");

const evaluate = new URLSearchParams({
  compound: compound.name,
  property_type: "apartment",
  area: "140",
  price: String(Math.round(((compound.classes[0]?.reference_ppm ?? 50000) * 140 * 1.35) / 1000) * 1000),
  down_payment: "1500000",
  installment_years: "6",
  delivery: String(new Date().getFullYear() + 2),
  finishing: "finished",
});
const pages = [
  ["home", "/"],
  ["evaluate", `/evaluate?${evaluate}`],
  ["evaluate-empty", "/evaluate"],
  ["units", "/units"],
  ["unit", `/units/${plan.id}`],
  ["unit-suspect", `/units/${unit.id}`],
  ["compounds", "/compounds?district=new-cairo"],
  ["compound", `/compounds/${encodeURIComponent(compound.key)}`],
  ...(launched ? [["compound-launch", `/compounds/${encodeURIComponent(launched.key)}`]] : []),
  ...(verified ? [["unit-aqarexit", `/units/${verified.id}`]] : []),
  ["developers", "/developers?sort=premium_desc"],
  ["developer", `/developers/${encodeURIComponent(developer.key)}`],
  ["compare", "/compare"],
  ["watchlist", "/watchlist"],
  ["methodology", "/methodology"],
];
const pinned = [
  { kind: "compound", key: compound.key, name: compound.name },
  { kind: "compound", key: second.key, name: second.name },
];
const viewports = {
  desktop: { viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 },
  mobile: { ...devices["iPhone 13"], viewport: { width: 390, height: 844 } },
};

const report = [];
const failures = [];
for (const [device, options] of Object.entries(viewports)) {
  for (const language of ["ar", "en"]) {
    const context = await browser.newContext(options);
    context.setDefaultTimeout(20_000);
    await context.addInitScript(
      ([lang, items]) => {
        localStorage.setItem("qayem:language", lang);
        localStorage.setItem("qayem:compare-entities", JSON.stringify(items));
        localStorage.setItem("qayem:watch", JSON.stringify(items));
      },
      [language, pinned],
    );
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
    page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));
    page.on("response", (r) => r.url().includes("/api/") && !r.ok() && errors.push(`api ${r.status()}: ${r.url()}`));
    for (const [name, path] of pages) {
      errors.length = 0;
      await page.goto(`${baseURL}${path}`, { waitUntil: "networkidle" });
      await page.waitForFunction(() => !document.querySelector(".state-loading"), null, { timeout: 30_000 });
      await page.waitForTimeout(700);
      const audit = await page.evaluate(([lang, names]) => {
        const width = window.innerWidth;
        const scrollers = ".ledger:not(.stack), .coverage-scroll, .formula-card code, .compare-table";
        const overflow = [...document.querySelectorAll("body *")]
          .filter((e) => {
            const box = e.getBoundingClientRect();
            return box.width && (box.right > width + 1 || box.left < -1) && !e.closest(scrollers) && getComputedStyle(e).visibility !== "hidden";
          })
          .slice(0, 5)
          .map((e) => `${e.tagName.toLowerCase()}.${e.className} [${Math.round(e.getBoundingClientRect().left)}–${Math.round(e.getBoundingClientRect().right)}]`);
        const small = [...document.querySelectorAll("a[href], button, select, input")]
          .filter((e) => {
            const box = e.getBoundingClientRect();
            return box.width > 0 && box.height > 0 && (box.height < 24 || box.width < 24) && !e.closest(".ledger-title, .unit-place, p, small");
          })
          .slice(0, 5)
          .map((e) => `${e.tagName.toLowerCase()}:${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 24)}`);
        // Untranslated interface copy: Latin text in the Arabic UI once data (names, codes) is removed.
        const latin = [];
        if (lang === "ar") {
          const skip = "[dir=auto], [dir=ltr], code, option, datalist, .brand, .nav-lang, .kbd, .evidence q, .source-initial, .grade b, svg";
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          while (walker.nextNode() && latin.length < 5) {
            const node = walker.currentNode;
            if (!node.parentElement || node.parentElement.closest(skip)) continue;
            let text = node.textContent;
            for (const name of names) text = text.split(name).join("");
            text = text.replace(/\b(EGP|m²|log|Esc|EN|qayem|QAYEM|https)\b/g, "");
            if (/[A-Za-z]{3,}/.test(text)) latin.push(text.trim().slice(0, 80));
          }
        }
        return { docWidth: document.documentElement.scrollWidth, width, overflow, small, latin, title: document.title };
      }, [language, dataNames]);
      const shot = `${device}-${language}-${name}.png`;
      await page.screenshot({ path: `${artifacts}${shot}`, fullPage: true });
      const entry = { device, language, name, ...audit, errors: [...errors] };
      report.push(entry);
      if (errors.length || audit.docWidth > audit.width + 1 || audit.overflow.length || audit.latin.length)
        failures.push(entry);
    }
    await context.close();
  }
}

// Interaction: evaluate a unit through the form on a phone, in English.
const context = await browser.newContext({ ...viewports.mobile });
await context.addInitScript(() => localStorage.setItem("qayem:language", "en"));
const page = await context.newPage();
await page.goto(`${baseURL}/evaluate`);
await page.getByLabel("Compound", { exact: true }).fill(compound.name);
await page.getByLabel("Area (m²)").fill("150");
await page.getByLabel("Headline price (EGP)").fill("9000000");
await page.getByRole("button", { name: "Installments" }).click();
await page.getByLabel("Paid at signing (EGP)").fill("2000000");
await page.getByLabel("Years of installments left").fill("5");
await page.getByRole("button", { name: "Value this unit" }).click();
await page.getByText("Qayem fair value · cash today").waitFor();
assert.match(page.url(), /installment_years=5/);
await page.getByText("Total cost of buying").waitFor();
await page.screenshot({ path: `${artifacts}flow-evaluate-mobile.png`, fullPage: true });
await context.close();

await browser.close();
await writeFile(`${artifacts}smoke-report.json`, JSON.stringify(report, null, 2));
if (failures.length) {
  console.error(JSON.stringify(failures, null, 2));
  process.exit(1);
}
console.log(`✓ ${report.length} page checks (${pages.length} pages × desktop/mobile × ar/en) and the evaluate flow passed`);
