// Browser check: analytics screen. Needs a RUNNING stack (API :8000 seeded dev
// data, built control centre :3001), playwright-core (not a repository
// dependency) and Chromium (CHROMIUM_PATH). Not part of check.sh. Creates an
// incident, a unit, a dispatch and a resolution in the dev DB so the time
// measures have a sample.
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e) => (await call("POST", "/auth/login", { email: e, password: PW })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";

const disp = await login("dispatcher@raksha.example"), cit = await login("citizen@raksha.example");
const tag = Date.now().toString(36).slice(-4).toUpperCase();
// Give the time measures at least one complete case: report -> dispatch -> resolved.
const unit = await call("POST", "/resources", { call_sign: "AN-" + tag, name: "Analytics unit", resource_type: "AMBULANCE", latitude: 13.0827, longitude: 80.2707 }, disp.access_token);
const REPORT = { category: "MEDICAL", description: "Analytics e2e " + tag + " person collapsed", latitude: 13.0827, longitude: 80.2707, medical_required: true, immediate_danger: true };
const inc = await call("POST", "/incidents", REPORT, cit.access_token);
await call("POST", `/incidents/${inc.body.id}/dispatches`, { resource_id: unit.body.id }, disp.access_token);
for (const to of ["RECEIVED", "UNDER_REVIEW", "PRIORITIZED", "ASSIGNED", "RESOLVED"]) {
  const r = await call("POST", `/incidents/${inc.body.id}/status`, { status: to }, disp.access_token);
  if (r.status !== 200) { out.push(`INFO  status ${to} -> ${r.status}`); break; }
}
const apiResp = (await call("GET", "/analytics/response-time", null, disp.access_token)).body;
const apiRes = (await call("GET", "/analytics/resolution-time", null, disp.access_token)).body;
check("API has a non-empty sample for both time measures", apiResp.sample_size > 0 && apiRes.sample_size > 0);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
async function signIn(email, w = 1440, h = 1000) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage(); const problems = [];
  page.on("console", (m) => { if (/content security policy|refused to/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
  await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', email); await page.fill('input[name="password"]', PW);
  await page.click('button[type="submit"]');
  return { ctx, page, problems };
}

const d = await signIn("dispatcher@raksha.example");
await d.page.waitForURL("**/dashboard", { timeout: 15000 });
await d.page.getByRole("link", { name: "Analytics" }).click();
await d.page.getByRole("heading", { name: "ANALYTICS" }).waitFor();
await d.page.getByRole("region", { name: "Hotspots" }).waitFor({ timeout: 10000 });
await d.page.getByRole("button", { name: "All time" }).click();
await d.page.waitForTimeout(1500);
const text = (await d.page.locator("body").innerText()).replace(/\s+/g, " ");
const allResp = (await call("GET", "/analytics/response-time", null, disp.access_token)).body;
check("response-time card shows the API's sample size", new RegExp(`from ${allResp.sample_size} incidents?`).test(text));
check("both time cards, category, resource and hotspot sections present", ["Time to first dispatch", "Time to resolution", "Incidents by category", "Resource use", "Where incidents cluster"].every((t) => text.includes(t)));
const cat = (await call("GET", "/analytics/category-breakdown", null, disp.access_token)).body;
check(`category total matches the API (${cat.total})`, text.includes(`${cat.total} incidents in the period`));
const hot = (await call("GET", "/analytics/hotspots", null, disp.access_token)).body;
check("hotspots show coarsened cell centres only", hot.items.length > 0 && !text.includes("13.0827") && !text.includes("80.2707") && text.includes(hot.items[0].latitude.toFixed(2)));
check("states the cell size and that locations are not individual reports", /about 1\.1 km across/.test(text) && /never an individual report/i.test(text));
check("says nothing predicts future incidents", /nothing here predicts future incidents/i.test(text));
await d.page.screenshot({ path: `${SHOT}/analytics-1.png`, fullPage: true });

// period narrows
await d.page.getByRole("button", { name: "Last 24 hours" }).click();
await d.page.waitForTimeout(1500);
const since = new Date(Date.now() - 24 * 3_600_000).toISOString();
const day = (await call("GET", `/analytics/category-breakdown?since=${encodeURIComponent(since)}`, null, disp.access_token)).body;
check(`24 h period uses a narrower window (${day.total} <= ${cat.total})`, day.total <= cat.total && (await d.page.locator("body").innerText()).includes(`${day.total} incidents in the period`));
// category filter
await d.page.getByLabel("Filter by category").selectOption("MEDICAL");
await d.page.waitForTimeout(1500);
const medical = (await call("GET", `/analytics/response-time?since=${encodeURIComponent(since)}&category=MEDICAL`, null, disp.access_token)).body;
check("category filter changes the time cards to the API's MEDICAL figure", new RegExp(`from ${medical.sample_size} incidents?`).test((await d.page.locator("body").innerText()).replace(/\s+/g, " ")) || medical.sample_size === 0);
check("no console/CSP errors", d.problems.length === 0);
await d.ctx.close();

// who cannot see it
// (a responder is not admitted to the control centre at all — responder-scope.mjs)
for (const [email, label] of [["hospital@raksha.example", "hospital operator"]]) {
  const s = await signIn(email);
  await s.page.waitForTimeout(2500);
  check(`${label} sees no Analytics link`, (await s.page.getByRole("link", { name: "Analytics" }).count()) === 0);
  await s.page.goto("http://localhost:3001/analytics", { waitUntil: "networkidle" });
  await s.page.waitForTimeout(1500);
  check(`${label} typing /analytics is sent home`, !/\/analytics$/.test(s.page.url()));
  await s.ctx.close();
}
const rLogin = await login("responder@raksha.example");
check("API refuses analytics to a responder (403)", (await call("GET", "/analytics/hotspots", null, rLogin.access_token)).status === 403);

const m = await signIn("dispatcher@raksha.example", 390, 844);
await m.page.waitForURL("**/dashboard");
await m.page.goto("http://localhost:3001/analytics", { waitUntil: "networkidle" });
await m.page.getByRole("region", { name: "Hotspots" }).waitFor({ timeout: 10000 });
check("mobile: no horizontal overflow", !(await m.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));
await m.page.screenshot({ path: `${SHOT}/analytics-mobile.png`, fullPage: true });
await browser.close();
console.log(out.join("\n"));
