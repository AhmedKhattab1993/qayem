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
const unit = (await api("/units?level=strong&page_size=1")).items[0];
const plan = (await api("/units?terms=plan&level=in_line&page_size=1")).items[0];
const unrated = (await api("/units?level=unrated&page_size=1")).items[0];
const compound = (await api("/compounds?page_size=1")).items[0];
const developer = (await api("/developers?sort=gap_asc&page_size=1")).items[0];
const second = (await api("/compounds?page_size=2&page=1")).items[1];
const catalog = await api("/catalog");
const launched = (await api("/compounds?page_size=100")).items.find((c) => c.launch);
const verified = (await api("/units?source=aqarexit&terms=plan&page_size=1")).items[0];
const belowDeveloper = (await api("/units?sort=launch_gap&page_size=1")).items[0];
const belowPeers = (await api("/units?sort=peer_gap&page_size=1")).items[0];
// Data never needs translating: entity names, source names, source-quoted evidence.
const dataNames = [
  ...catalog.compounds.map((c) => c.name),
  ...catalog.developers.map((d) => d.name),
  ...catalog.districts.map((d) => d.name),
  ...overview.sources.map((s) => s.name),
]
  .filter((name) => /[A-Za-z]/.test(name))
  .sort((a, b) => b.length - a.length);
assert.ok(overview.rated_count > 0 && unit && plan && compound && developer, "catalog has compared units");

const evaluate = new URLSearchParams({
  compound: compound.name,
  property_type: "apartment",
  area: "140",
  price: String(Math.round(((compound.classes[0]?.median_asking_ppm ?? 50000) * 140 * 0.85) / 1000) * 1000),
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
  ["unit-strong", `/units/${unit.id}`],
  ...(unrated ? [["unit-unrated", `/units/${unrated.id}`]] : []),
  ...(belowPeers ? [["unit-peers", `/units/${belowPeers.id}`]] : []),
  ["compounds", "/compounds?district=new-cairo"],
  ["compound", `/compounds/${encodeURIComponent(compound.key)}`],
  ...(launched ? [["compound-launch", `/compounds/${encodeURIComponent(launched.key)}`]] : []),
  ...(verified ? [["unit-aqarexit", `/units/${verified.id}`]] : []),
  ...(belowDeveloper
    ? [
        ["unit-developer", `/units/${belowDeveloper.id}`],
        ["units-developer", "/units?sort=launch_gap"],
      ]
    : []),
  ["developers", "/developers?sort=gap_asc"],
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
      ([lang, items, saved]) => {
        localStorage.setItem("qayem:language", lang);
        localStorage.setItem("qayem:compare-entities", JSON.stringify(items));
        localStorage.setItem("qayem:watch", JSON.stringify(saved));
      },
      [language, pinned, [...pinned, { kind: "unit", key: String(unit.id), name: "Saved unit" }]],
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
        const scrollers = ".ledger:not(.stack), .coverage-scroll, .formula-card code, .compare-table, .gallery-track";
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
          const skip = "[dir=auto], [dir=ltr], bdi, code, option, datalist, .brand, .nav-lang, .kbd, .evidence q, .source-initial, .grade b, svg";
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
await page.goto(`${baseURL}/evaluate`, { waitUntil: "networkidle" });
await page.getByLabel("Compound", { exact: true }).fill(compound.name);
await page.getByLabel("Area (m²)").fill("150");
await page.getByLabel("Headline price (EGP)").fill("9000000");
await page.getByRole("button", { name: "Installments" }).click();
await page.getByLabel("Paid at signing (EGP)").fill("2000000");
await page.getByLabel("Years of installments left").fill("5");
await page.getByRole("button", { name: "Compare this unit" }).click();
await page.locator(".opportunity, .field-error").first().waitFor();
assert.equal(await page.locator(".field-error").count(), 0, await page.locator(".field-error").textContent().catch(() => ""));
await page.getByText("Vs similar units listed now").waitFor();
assert.match(page.url(), /installment_years=5/);
await page.getByText("Total cost of buying").waitFor();
await page.screenshot({ path: `${artifacts}flow-evaluate-mobile.png`, fullPage: true });

// Interaction: on a phone the unit filters fold behind a button, the sort stays reachable, and a whole card opens its unit.
await page.goto(`${baseURL}/units`, { waitUntil: "networkidle" });
assert.equal(await page.locator("#unit-filters").isVisible(), false, "filters start folded on a phone");
await page.getByRole("button", { name: /Filters/ }).click();
await page.getByLabel("Unit type").selectOption("apartment");
await page.getByLabel("Sort by").selectOption("price_asc");
await page.waitForURL(/property_type=apartment.*sort=price_asc|sort=price_asc.*property_type=apartment/);
await page.locator(".unit-ledger tbody tr").first().click({ position: { x: 300, y: 110 } });
await page.waitForURL(/\/units\/\d+$/);

// The unit's main figures come first, one tile each: an installment unit shows its value in today's money.
await page.goto(`${baseURL}/units/${plan.id}`, { waitUntil: "networkidle" });
const glance = page.getByRole("region", { name: "At a glance" });
for (const label of ["Total price", "Worth in today’s money", "Paid at signing", "Area", "Price per m²"])
  await glance.getByText(label, { exact: true }).waitFor();
assert.equal(await glance.locator(".glance-tile.is-feature").count(), 1, "one highlighted tile");
await context.close();

// The explainer film: only a poster until asked, then the phone-sized file on a phone, and it plays.
// Safari will not play a video from a server that ignores byte ranges.
const film = await fetch(`${baseURL}/media/explainer-v4-720.mp4`, { headers: { Range: "bytes=0-1023" } });
assert.equal(film.status, 206, "the explainer is served in byte ranges");
for (const [device, file] of [["mobile", "720"], ["desktop", "1080"]]) {
  const context = await browser.newContext({ ...viewports[device] });
  await context.addInitScript(() => localStorage.setItem("qayem:language", "en"));
  const page = await context.newPage();
  const requested = [];
  page.on("request", (r) => r.url().endsWith(".mp4") && requested.push(r.url()));
  await page.goto(`${baseURL}/`, { waitUntil: "networkidle" });
  assert.deepEqual(requested, [], "no video is fetched before play");
  await page.getByRole("link", { name: /Watch how it works/ }).click();
  await page.waitForFunction(() => (document.querySelector("#explainer video")?.currentTime ?? 0) > 0.5, null, { timeout: 30_000 });
  assert.ok(requested.length && requested.every((url) => url.endsWith(`-${file}.mp4`)), `${device} plays the ${file}p file: ${requested}`);
  await page.screenshot({ path: `${artifacts}flow-explainer-${device}.png` });
  await context.close();
}

await browser.close();
await writeFile(`${artifacts}smoke-report.json`, JSON.stringify(report, null, 2));
if (failures.length) {
  console.error(JSON.stringify(failures, null, 2));
  process.exit(1);
}
console.log(`✓ ${report.length} page checks (${pages.length} pages × desktop/mobile × ar/en) and the evaluate, units and explainer flows passed`);
