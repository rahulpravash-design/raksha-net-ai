// Browser check: resource inventory screen and the redesigned incident detail.
// Needs a RUNNING stack (API :8000 seeded dev data, built control centre :3001),
// playwright-core (not a repository dependency) and Chromium (CHROMIUM_PATH).
// Not part of check.sh. Creates a resource and an incident in the dev DB.
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e) => (await call("POST", "/auth/login", { email: e, password: PW })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";

const disp = await login("dispatcher@raksha.example"), resp = await login("responder@raksha.example"), cit = await login("citizen@raksha.example");
const tag = Date.now().toString(36).slice(-4).toUpperCase();
const inc = await call("POST", "/incidents", { category: "FIRE", description: "Warehouse fire, workers unaccounted for (detail e2e " + tag + ")", latitude: 13.09, longitude: 80.28, people_affected: 3, people_trapped: true, immediate_danger: true }, cit.access_token);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
async function signIn(email, w = 1440, h = 1000) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage(); const problems = [];
  page.on("console", (m) => { if (/content security policy|refused to|error/i.test(m.text()) && !/tile\.openstreetmap|ERR_(NAME|INTERNET|CONNECTION|TUNNEL|PROXY)|Failed to load resource/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
  await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', email); await page.fill('input[name="password"]', PW);
  await page.click('button[type="submit"]'); await page.waitForURL("**/dashboard", { timeout: 15000 });
  return { ctx, page, problems };
}

// ---- resource inventory (dispatcher) --------------------------------------
const { ctx, page, problems } = await signIn("dispatcher@raksha.example");
await page.getByRole("link", { name: "Resources" }).click();
await page.waitForURL("**/resources");
await page.getByRole("heading", { name: "RESOURCES" }).waitFor();
await page.waitForTimeout(800);
check("sidebar marks Resources active", (await page.locator('nav[aria-label="Modules"] a[aria-current="page"]').innerText()) === "Resources");
const stats = await call("GET", "/resources/stats/summary", null, disp.access_token);
check(`stats tile matches the API (${stats.body.total_active})`, (await page.locator("dl").first().innerText()).includes(String(stats.body.total_active)));

// validation
await page.getByRole("button", { name: "Register a resource" }).click();
await page.getByRole("button", { name: "Register resource" }).click();
check("empty form shows field errors and sends nothing", (await page.getByText(/latitude must be a number/i).count()) === 1);
// create
const sign = "UI-" + tag;
await page.getByLabel(/call sign/i).fill(sign);
await page.getByLabel(/^name/i).fill("UI Rescue Boat");
await page.getByLabel("Type", { exact: true }).selectOption("RESCUE_BOAT");
await page.getByLabel(/latitude/i).fill("13.10"); await page.getByLabel(/longitude/i).fill("80.30");
await page.getByLabel(/capabilities/i).fill("Swift_Water, night");
await page.getByRole("button", { name: "Register resource" }).click();
await page.getByRole("region", { name: "Resource detail" }).waitFor();
const created = await call("GET", `/resources?q=${sign}`, null, disp.access_token);
check("resource exists server-side with normalised capabilities", created.body.items?.[0]?.call_sign === sign && created.body.items[0].capabilities.join() === "swift_water,night" && created.body.items[0].status === "AVAILABLE");
// duplicate call sign: server message surfaced
await page.getByRole("button", { name: "Register a resource" }).click();
await page.getByLabel(/call sign/i).fill(sign); await page.getByLabel(/^name/i).fill("Dup");
await page.getByLabel(/latitude/i).fill("13.1"); await page.getByLabel(/longitude/i).fill("80.3");
await page.getByRole("button", { name: "Register resource" }).click();
await page.getByRole("alert").filter({ hasText: /already exists/i }).waitFor({ timeout: 8000 });
check("duplicate call sign refused, server message shown", true);
await page.getByRole("button", { name: "Cancel" }).click();

// select, set out of service
await page.getByRole("button", { name: new RegExp(sign) }).click();
const detail = page.getByRole("region", { name: "Resource detail" });
await detail.getByRole("button", { name: /set out of service/i }).click();
await detail.getByText("Out of service").first().waitFor();
const after = await call("GET", `/resources/${created.body.items[0].id}`, null, disp.access_token);
check("server status is OUT_OF_SERVICE", after.body.status === "OUT_OF_SERVICE");
await page.screenshot({ path: `${SHOT}/res-1-inventory.png` });
// filters
await page.getByLabel("Filter by status").selectOption("OUT_OF_SERVICE");
await page.waitForTimeout(900);
check("status filter shows the unit", (await page.getByRole("list", { name: "Resources" }).innerText()).includes(sign));
await page.getByLabel("Filter by status").selectOption("AVAILABLE"); await page.waitForTimeout(900);
check("status filter excludes it under Available", !(await page.getByRole("list", { name: "Resources" }).innerText().catch(() => "")).includes(sign));
await page.getByLabel("Filter by status").selectOption("");
// edit
await page.getByRole("button", { name: new RegExp(sign) }).click();
await detail.getByRole("button", { name: "Edit details" }).click();
await detail.getByLabel(/^name/i).fill("UI Rescue Boat Mk2");
await detail.getByRole("button", { name: "Save changes" }).click();
await detail.getByText("UI Rescue Boat Mk2").first().waitFor();
// deactivate
await detail.getByRole("button", { name: "Deactivate…" }).click();
check("deactivate needs a second step", (await call("GET", `/resources/${created.body.items[0].id}`, null, disp.access_token)).body.is_active === true);
await detail.getByRole("button", { name: "Confirm deactivate" }).click();
await page.waitForTimeout(1200);
const gone = await call("GET", `/resources?q=${sign}&active_only=true`, null, disp.access_token);
check("deactivated unit leaves the active inventory", gone.body.items.length === 0);
check("no console/CSP errors (inventory)", problems.length === 0);
if (problems.length) out.push("   " + problems.join(" | "));
await ctx.close();

// ---- role: responder gets read-only, API refuses writes ---------------------
const r = await call("POST", "/resources", { call_sign: "NOPE-" + tag, name: "Nope", resource_type: "AMBULANCE", latitude: 13, longitude: 80 }, resp.access_token);
check("responder cannot register a resource (403)", r.status === 403);
try {
  const rs = await signIn("responder@raksha.example");
  await rs.page.goto("http://localhost:3001/resources", { waitUntil: "networkidle" });
  await rs.page.waitForTimeout(1200);
  const body = await rs.page.locator("body").innerText();
  check("responder sees no Register button in the control centre", !/Register a resource/.test(body));
  await rs.ctx.close();
} catch { out.push("INFO  responder is not admitted to the control-centre UI (sign-in did not reach /dashboard)"); }

// ---- incident detail ----------------------------------------------------------
const d = await signIn("dispatcher@raksha.example");
await d.page.getByRole("button", { name: new RegExp(inc.body.reference_code) }).click();
await d.page.getByRole("region", { name: "Selected incident" }).waitFor();
await d.page.getByRole("button", { name: "Quick view" }).click();
const dialog = d.page.getByRole("dialog", { name: "Incident details" });
await dialog.waitFor();
check("quick-view drawer shows the reported words", (await dialog.innerText()).includes("Warehouse fire"));
check("drawer states facts are unverified", /not independently verified/i.test(await dialog.innerText()));
check("focus moved into the drawer", await d.page.evaluate(() => document.activeElement?.textContent === "Close"));
await d.page.screenshot({ path: `${SHOT}/detail-1-drawer.png` });
await d.page.keyboard.press("Escape");
await d.page.waitForTimeout(500);
check("Escape closes the drawer", (await d.page.getByRole("dialog").count()) === 0);
check("focus returns to Quick view", await d.page.evaluate(() => document.activeElement?.textContent === "Quick view"));
await d.page.getByRole("button", { name: "Quick view" }).click();
await d.page.getByRole("dialog").getByRole("link", { name: /open incident console/i }).click();
await d.page.waitForURL(/\/incidents\//);
await d.page.getByRole("heading", { name: "Fire" }).waitFor();
const facts = await d.page.getByRole("list", { name: "Key facts" }).innerText();
check("header chips: trapped, danger, affected", /People trapped/.test(facts) && /Immediate danger/.test(facts) && /3 affected/.test(facts));
const sit = d.page.getByRole("button", { name: "Reported situation" });
check("situation panel open by default", (await sit.getAttribute("aria-expanded")) === "true");
await sit.click();
await d.page.waitForTimeout(700);
check("collapsing hides the words", await d.page.getByText("Warehouse fire").count() === 0 || !(await d.page.getByText(/Warehouse fire/).first().isVisible().catch(() => false)));
await sit.click();
await d.page.getByText(/Warehouse fire/).first().waitFor();
// regression: the extracted actions still work
await d.page.getByLabel("Note").first().fill("Reviewing now");
await d.page.getByRole("button", { name: "Under review" }).click();
await d.page.getByText("Reported → Under review").waitFor({ timeout: 8000 });
check("status move still works and the timeline shows it as current", /current/.test(await d.page.getByText("Reported → Under review").locator("..").innerText()));
const hist = await call("GET", `/incidents/${inc.body.id}/history`, null, disp.access_token);
check("history recorded server-side with the note", JSON.stringify(hist.body).includes("Reviewing now"));
await d.page.screenshot({ path: `${SHOT}/detail-2-console.png`, fullPage: true });
check("no console/CSP errors (incident)", d.problems.length === 0);
if (d.problems.length) out.push("   " + d.problems.join(" | "));
await d.ctx.close();

// mobile
const m = await signIn("dispatcher@raksha.example", 390, 844);
await m.page.goto("http://localhost:3001/resources", { waitUntil: "networkidle" });
await m.page.waitForTimeout(1200);
check("mobile: resources has no horizontal overflow", !(await m.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));
await m.page.screenshot({ path: `${SHOT}/res-2-mobile.png`, fullPage: true });
await m.page.goto(`http://localhost:3001/incidents/${inc.body.id}`, { waitUntil: "networkidle" });
await m.page.waitForTimeout(1200);
check("mobile: incident detail has no horizontal overflow", !(await m.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));
await browser.close();
console.log(out.join("\n"));
