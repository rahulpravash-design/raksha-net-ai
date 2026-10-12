// Browser check: the landing page globe shows REAL incidents to a signed-in dispatch-side
// user, labelled demonstration markers to everyone else, and never real locations to a visitor.
// Needs a RUNNING stack (API :8000 seeded dev data, built control centre :3001),
// playwright-core (not a repository dependency) and Chromium (CHROMIUM_PATH).
// Not part of check.sh. Creates two incidents in the dev DB. Prints PASS/FAIL per check.
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", APP = "http://localhost:3001", PW = "raksha-development-only";
const SHOT = process.env.SHOT_DIR ?? ".";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e) => (await call("POST", "/auth/login", { email: e, password: PW })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const cit = await login("citizen@raksha.example");
const disp = await login("dispatcher@raksha.example");
const tag = Date.now().toString(36).slice(-4).toUpperCase();
const make = (desc, extra = {}) => call("POST", "/incidents", { category: "FIRE", description: `${desc} (landing e2e ${tag})`, latitude: 13.09, longitude: 80.28, people_affected: 4, people_trapped: true, immediate_danger: true, ...extra }, cit.access_token);
const first = await make("Warehouse fire, people trapped");
const openNow = async () => (await call("GET", "/incidents/stats/summary", null, disp.access_token)).body.total_open;
const queue = async () => (await call("GET", "/incidents?open_only=true&sort=priority&page_size=50", null, disp.access_token)).body.items;

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });

async function open(opts = {}, w = 1440, h = 900) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, ...opts });
  const page = await ctx.newPage(); const problems = [], incidentCalls = [];
  page.on("console", (m) => { if (/content security policy|refused to|error/i.test(m.text()) && !/tile\.openstreetmap|ERR_(NAME|INTERNET|CONNECTION|TUNNEL|PROXY)|Failed to load resource/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
  page.on("request", (r) => { if (/\/api\/v1\/incidents/.test(r.url())) incidentCalls.push(r.url()); });
  return { ctx, page, problems, incidentCalls };
}
async function signIn(page, email) {
  await page.goto(`${APP}/login`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', email); await page.fill('input[name="password"]', PW);
  await page.click('button[type="submit"]'); await page.waitForURL(/\/(dashboard|hospitals)$/, { timeout: 15000 });
}
const text = async (page) => (await page.locator("body").innerText()).replace(/\s+/g, " ");
const noOverflow = (page) => page.evaluate(() => !(document.documentElement.scrollWidth > document.documentElement.clientWidth));

// ---- a visitor ---------------------------------------------------------------------
{
  const v = await open();
  await v.page.goto(`${APP}/`, { waitUntil: "networkidle" }); await v.page.waitForTimeout(2500);
  const body = await text(v.page);
  check("visitor: globe canvas rendered", (await v.page.locator("canvas").count()) > 0);
  check("visitor: markers are labelled demonstration, not live", /Demonstration markers — not live incidents/i.test(body));
  check("visitor: told to sign in for live incidents", /sign in to see live incidents/i.test(body));
  check("visitor: no incident endpoint was called", v.incidentCalls.length === 0);
  check("visitor: no real reference code anywhere on the page", !body.includes(first.body.reference_code));
  check("visitor: platform section has six 'Sign in to open' cards", (await v.page.getByRole("link", { name: /Sign in to open/ }).count()) === 6);
  check("visitor: states the visuals are not an emergency service", /do not themselves provide emergency services/.test(body));
  check("visitor: no console/CSP errors", v.problems.length === 0);
  await v.page.screenshot({ path: `${SHOT}/landing-visitor.png`, fullPage: true });
  await v.ctx.close();
}

// ---- a dispatcher ----------------------------------------------------------------------
{
  const d = await open();
  await signIn(d.page, "dispatcher@raksha.example");
  await d.page.goto(`${APP}/`, { waitUntil: "networkidle" });
  const live = d.page.getByRole("region", { name: "Live incidents" });
  await live.waitFor({ timeout: 15000 });
  const total = await openNow();
  await d.page.getByRole("status").filter({ hasText: "open incident" }).waitFor({ timeout: 15000 });
  const body = await text(d.page);
  check(`dispatcher: count equals the API's open total (${total})`, new RegExp(`\\b${total} open incidents?`).test(body));
  check("dispatcher: no demonstration markers", !/Demonstration markers/i.test(body));
  check("dispatcher: globe canvas rendered", (await d.page.locator("canvas").count()) > 0);
  const expected = (await queue()).slice(0, 8).map((i) => i.reference_code);
  const chips = (await live.getByRole("button").allInnerTexts()).map((t) => t.match(/RKS-[A-Z0-9]+/)?.[0]);
  check(`dispatcher: chips are the API's top ${expected.length} by priority, in order`, JSON.stringify(chips) === JSON.stringify(expected));
  check("dispatcher: greeted by name and role", /Dispatcher/.test(await d.page.locator("header").innerText()));
  check("dispatcher: platform section has six open links", (await d.page.getByRole("link", { name: /^Open / }).count()) >= 6);

  await live.getByRole("button").first().click();
  const link = d.page.getByRole("link", { name: "Open this incident" });
  await link.waitFor({ timeout: 5000 });
  const href = await link.getAttribute("href");
  check("dispatcher: selecting a chip offers that incident's page", /^\/incidents\/[0-9a-f-]{36}$/.test(href ?? ""));
  const sel = await text(d.page);
  check("dispatcher: the landing page never shows report text", !/landing e2e/.test(sel));
  await d.page.screenshot({ path: `${SHOT}/landing-dispatcher.png`, fullPage: false });
  await link.click(); await d.page.waitForURL("**/incidents/**", { timeout: 10000 });
  await d.page.waitForTimeout(1500);
  check("dispatcher: the link opens the real incident page", /RKS-/.test(await text(d.page)));

  // a new report appears within the refresh window
  await d.page.goto(`${APP}/`, { waitUntil: "networkidle" });
  await d.page.getByRole("status").filter({ hasText: "open incident" }).waitFor({ timeout: 15000 });
  const before = await openNow();
  await make("Second report during the live check", { people_trapped: false });
  let seen = false;
  for (let i = 0; i < 30 && !seen; i++) { await sleep(1000); seen = new RegExp(`\\b${before + 1} open incidents?`).test(await text(d.page)); }
  check(`dispatcher: a new report raised the count to ${before + 1} without a reload`, seen);
  check("dispatcher: no console/CSP errors", d.problems.length === 0);
  await d.ctx.close();
}

// ---- a hospital operator ------------------------------------------------------------------
{
  const h = await open();
  await signIn(h.page, "hospital@raksha.example");
  h.incidentCalls.length = 0;
  await h.page.goto(`${APP}/`, { waitUntil: "networkidle" }); await h.page.waitForTimeout(2000);
  const body = await text(h.page);
  check("hospital operator: demonstration markers, with the reason", /Demonstration markers/i.test(body) && /limited to dispatch staff/i.test(body));
  check("hospital operator: no incident endpoint was called from the landing page", h.incidentCalls.length === 0);
  check("hospital operator: call to action opens hospitals", (await h.page.getByRole("link", { name: "OPEN HOSPITALS" }).getAttribute("href")) === "/hospitals");
  check("hospital operator: five cards say 'Not available to your role'", (await h.page.getByText("Not available to your role").count()) === 5);
  await h.ctx.close();
}

// ---- phone, reduced motion, no WebGL -----------------------------------------------------------
{
  const m = await open({ isMobile: true, hasTouch: true }, 390, 844);
  await signIn(m.page, "dispatcher@raksha.example");
  await m.page.goto(`${APP}/`, { waitUntil: "networkidle" });
  await m.page.getByRole("region", { name: "Live incidents" }).waitFor({ timeout: 15000 });
  await m.page.waitForTimeout(1500);
  check("mobile: no horizontal overflow", await noOverflow(m.page));
  await m.page.screenshot({ path: `${SHOT}/landing-mobile.png`, fullPage: true });
  check("mobile: no console/CSP errors", m.problems.length === 0);
  await m.ctx.close();

  const r = await open({ reducedMotion: "reduce" });
  await signIn(r.page, "dispatcher@raksha.example");
  await r.page.goto(`${APP}/`, { waitUntil: "networkidle" });
  await r.page.getByRole("region", { name: "Live incidents" }).waitFor({ timeout: 15000 });
  check("reduced motion: globe and live list present", (await r.page.locator("canvas").count()) > 0);
  check("reduced motion: no console/CSP errors", r.problems.length === 0);
  await r.ctx.close();
}
await browser.close();

{
  const b2 = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--disable-gpu", "--disable-3d-apis", "--disable-webgl", "--disable-webgl2"] });
  const ctx = await b2.newContext({ viewport: { width: 1440, height: 900 } }); const page = await ctx.newPage();
  await signIn(page, "dispatcher@raksha.example");
  await page.goto(`${APP}/`, { waitUntil: "networkidle" });
  await page.getByRole("status").filter({ hasText: "open incident" }).waitFor({ timeout: 15000 });
  check("no WebGL: static globe fallback shown", (await page.locator("canvas").count()) === 0 && (await page.locator('[role="img"] svg').count()) > 0);
  check("no WebGL: the live incident list still works", /\d+ open incidents?/.test(await text(page)));
  await page.screenshot({ path: `${SHOT}/landing-nowebgl.png` });
  await b2.close();
}

console.log(out.join("\n"));
process.exit(out.some((l) => l.startsWith("FAIL")) ? 1 : 0);
