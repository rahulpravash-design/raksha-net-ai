// Browser check against a RUNNING stack (API :8000 seeded dev data; apps :3000/:3001/:3002 built).
// Needs playwright-core (not a repository dependency) and Chromium (CHROMIUM_PATH). Not part of check.sh.
// Creates incidents/resources in the dev DB. Prints PASS/FAIL per check.
import { chromium } from "playwright-core";
const out = [];
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
async function run(name, ctxOpts, w, h) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, ...ctxOpts });
  const page = await ctx.newPage();
  const problems = [];
  page.on("console", (m) => { if (/content security policy|refused to|error|warning/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
  await page.goto("http://localhost:3001/", { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  const hasCanvas = await page.locator("canvas").count();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  const heading = await page.locator("h1").innerText();
  const links = await page.evaluate(() => [...document.querySelectorAll("a")].map((a) => a.textContent.trim() + "→" + a.getAttribute("href")));
  out.push(`${name}: canvas=${hasCanvas} h1="${heading}" horizontalOverflow=${overflow}`);
  out.push(`  links: ${links.join(" | ")}`);
  if (hasCanvas) {
    const lit = await page.evaluate(() => { const c = document.querySelector("canvas"); return [c.width, c.height]; });
    out.push(`  canvas size ${lit}`);
  }
  out.push(`  problems: ${problems.length ? problems.join(" | ") : "none"}`);
  await page.screenshot({ path: `/tmp/claude-0/logs/landing-${name}.png` });
  await ctx.close();
}
await run("desktop", {}, 1440, 900);
await run("mobile", { isMobile: true, hasTouch: true }, 390, 844);
await run("reduced", { reducedMotion: "reduce" }, 1440, 900);
await browser.close();
// WebGL disabled
const b2 = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--disable-gpu", "--disable-3d-apis", "--disable-webgl", "--disable-webgl2"] });
const p2 = await (await b2.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
await p2.goto("http://localhost:3001/", { waitUntil: "networkidle" });
await p2.waitForTimeout(1500);
out.push(`no-webgl: canvas=${await p2.locator("canvas").count()} fallback=${await p2.locator('[role="img"] svg').count()} h1="${await p2.locator("h1").innerText()}"`);
await p2.screenshot({ path: `${process.env.SHOT_DIR ?? "."}/landing-nowebgl.png` });
await b2.close();
console.log(out.join("\n"));
