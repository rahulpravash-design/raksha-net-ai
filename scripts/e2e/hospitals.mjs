// Browser check: hospital capacity and inbound notices, for a dispatcher and for
// a hospital operator. Needs a RUNNING stack (API :8000 seeded dev data, built
// control centre :3001), playwright-core (not a repository dependency) and
// Chromium (CHROMIUM_PATH). Not part of check.sh. Creates hospitals/incidents.
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e) => (await call("POST", "/auth/login", { email: e, password: PW })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";

const admin = await login("admin@raksha.example"), disp = await login("dispatcher@raksha.example");
const hop = await login("hospital@raksha.example"), cit = await login("citizen@raksha.example");
const tag = Date.now().toString(36).slice(-4).toUpperCase();
const mine = await call("POST", "/hospitals", { code: "MINE-" + tag, name: "Mine General " + tag, latitude: 13.09, longitude: 80.27, total_beds: 80, available_beds: 20, icu_total: 10, icu_available: 2, specialties: ["trauma", "burns"], managed_by_id: hop.user.id }, admin.access_token);
const other = await call("POST", "/hospitals", { code: "OTH-" + tag, name: "Other Clinic " + tag, latitude: 13.1, longitude: 80.28, total_beds: 30, available_beds: 5 }, admin.access_token);
check("hospitals registered via API", mine.status === 201 && other.status === 201);
const SECRET = "Warehouse roof collapse, reporter phone details (hosp e2e " + tag + ")";
const inc = await call("POST", "/incidents", { category: "BUILDING_COLLAPSE", description: SECRET, latitude: 13.0827, longitude: 80.2707, people_affected: 2, people_trapped: true, medical_required: true, immediate_danger: true }, cit.access_token);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
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

// ---- dispatcher: hospitals screen ---------------------------------------------
const d = await signIn("dispatcher@raksha.example");
await d.page.waitForURL("**/dashboard", { timeout: 15000 });
await d.page.getByRole("link", { name: "Hospitals" }).click();
await d.page.getByRole("heading", { name: "HOSPITALS" }).waitFor();
await d.page.getByRole("button", { name: new RegExp("Mine General " + tag) }).waitFor();
const cardText = (await d.page.getByRole("button", { name: new RegExp("Mine General " + tag) }).innerText()).replace(/\s+/g, " ");
check("capacity shown in words", /20 of 80 beds free/.test(cardText) && /2 of 10 ICU beds free/.test(cardText));
check("card shows when capacity was reported (creation counts as a report)", /Reported .* ago/.test(cardText));
await d.page.getByLabel("Search hospitals").fill("Other Clinic " + tag);
check("search narrows the list", (await d.page.getByRole("list", { name: "Hospitals" }).locator("li").count()) === 1);
await d.page.getByLabel("Search hospitals").fill("Mine General " + tag);
await d.page.getByRole("button", { name: new RegExp("Mine General " + tag) }).click();
const detail = d.page.getByRole("region", { name: "Hospital detail" });
await detail.getByRole("button", { name: "Report capacity" }).click();
await detail.getByLabel("Free beds").fill("200");
await detail.getByRole("button", { name: "Report capacity" }).click();
check("free beds above total blocked client-side", await detail.getByText(/cannot exceed total beds/i).count() === 1);
await detail.getByLabel("Free beds").fill("15");
await detail.getByLabel(/^Note/).fill("Shift change");
await detail.getByRole("button", { name: "Report capacity" }).click();
await detail.getByText("15", { exact: true }).first().waitFor({ timeout: 8000 }).catch(() => {});
await d.page.waitForTimeout(1000);
const after = await call("GET", `/hospitals/${mine.body.id}`, null, disp.access_token);
check("server capacity updated, timestamp set", after.body.available_beds === 15 && after.body.capacity_updated_at !== null);
check("detail text reflects it", /15 of 80 beds free/.test((await detail.innerText()).replace(/\s+/g, " ")));
await d.page.screenshot({ path: `${SHOT}/hosp-1-dispatcher.png` });

// ---- dispatcher: notify from the incident ---------------------------------------
await d.page.goto("http://localhost:3001/incidents/" + inc.body.id, { waitUntil: "networkidle" });
await d.page.getByRole("heading", { name: "Hospitals" }).waitFor();
await d.page.getByRole("button", { name: /Notify a hospital/ }).click();
await d.page.getByRole("list", { name: "Nearby hospitals" }).waitFor();
const choose = d.page.getByRole("list", { name: "Nearby hospitals" }).locator("li", { hasText: "Mine General " + tag }).getByRole("button", { name: "Choose" });
await choose.click();
await d.page.getByLabel(/^ETA \(minutes\)/).fill("12");
await d.page.getByLabel(/^Clinical notes/).fill("Two crush injuries");
await d.page.getByRole("button", { name: "Review notice" }).click();
const pre = await call("GET", `/incidents/${inc.body.id}/hospital-notices`, null, disp.access_token);
check("nothing sent before the final confirmation", pre.body.length === 0);
check("review says what does not travel", /will not include the reporter, contact details, report text or location/i.test(await d.page.locator("body").innerText()));
await d.page.getByRole("button", { name: "Send notice" }).click();
await d.page.getByText("Mine General " + tag + " was notified").waitFor({ timeout: 8000 });
const post = await call("GET", `/incidents/${inc.body.id}/hospital-notices`, null, disp.access_token);
check("one notice, NOTIFIED, with only the intended fields", post.body.length === 1 && post.body[0].status === "NOTIFIED" && post.body[0].eta_minutes === 12 && post.body[0].clinical_notes === "Two crush injuries");
check("notice payload has no reporter/text/location", !/description|reporter|contact_phone|latitude|longitude|address/.test(JSON.stringify(post.body)));
check("dispatcher is offered Withdraw, not Acknowledge", (await d.page.getByRole("button", { name: /withdraw notice/i }).count()) === 1 && (await d.page.getByRole("button", { name: "Acknowledge" }).count()) === 0);
await d.page.screenshot({ path: `${SHOT}/hosp-2-notify.png`, fullPage: true });
check("no console/CSP errors (dispatcher)", d.problems.length === 0);
await d.ctx.close();

// ---- hospital operator -----------------------------------------------------------
const h = await signIn("hospital@raksha.example");
await h.page.waitForURL("**/hospitals", { timeout: 15000 });
check("hospital operator lands on /hospitals, not the dashboard", /\/hospitals$/.test(h.page.url()));
const nav = await h.page.locator('nav[aria-label="Modules"]').innerText();
check("sidebar offers no incident or resource screens", !/Command centre|Resources/.test(nav) && /Hospitals/.test(nav));
await h.page.getByRole("button", { name: new RegExp("Mine General " + tag) }).waitFor();
const first = await h.page.getByRole("list", { name: "Hospitals" }).locator("li").first().innerText();
check("their own hospital is listed first, marked", /your hospital/i.test(first));
await h.page.getByRole("button", { name: new RegExp("Mine General " + tag) }).click();
const hd = h.page.getByRole("region", { name: "Hospital detail" });
await hd.getByText(/2 patients/).waitFor({ timeout: 8000 });
const hText = await h.page.locator("body").innerText();
check("notice shows ETA and clinical notes", /ETA about 12 min/.test(hText) && /Two crush injuries/.test(hText));
check("the report text and reporter never reach the page", !hText.includes("Warehouse roof collapse") && !hText.includes("Asha Ramanathan"));
await h.page.getByRole("button", { name: new RegExp("Other Clinic " + tag) }).click();
check("another hospital's inbound list is not offered", /visible to this hospital's own operators and to dispatchers/i.test(await h.page.getByRole("region", { name: "Hospital detail" }).innerText()));
await h.page.getByRole("button", { name: new RegExp("Mine General " + tag) }).click();
await h.page.getByRole("button", { name: "Divert…" }).click();
check("divert needs a reason", await h.page.getByRole("button", { name: "Confirm divert" }).isDisabled());
await h.page.getByRole("button", { name: "Back" }).click();
await h.page.getByRole("button", { name: "Acknowledge" }).click();
let ack;
for (let i = 0; i < 20; i++) {
  ack = await call("GET", `/incidents/${inc.body.id}/hospital-notices`, null, disp.access_token);
  if (ack.body[0]?.status === "ACKNOWLEDGED") break;
  await h.page.waitForTimeout(250);
}
await h.page.getByRole("list", { name: "Inbound notices" }).getByText("Acknowledged", { exact: true }).waitFor({ timeout: 8000 });
check("server notice is ACKNOWLEDGED", ack.body[0].status === "ACKNOWLEDGED");
await h.page.screenshot({ path: `${SHOT}/hosp-3-operator.png` });
await h.page.goto("http://localhost:3001/dashboard", { waitUntil: "networkidle" });
await h.page.waitForURL("**/hospitals", { timeout: 8000 });
check("typing /dashboard bounces the operator back to /hospitals", /\/hospitals$/.test(h.page.url()));
const apiIncident = await call("GET", `/incidents/${inc.body.id}`, null, hop.access_token);
check("API refuses the operator the incident record", apiIncident.status === 403 || apiIncident.status === 404);
check("API refuses the operator the incident queue (403)", (await call("GET", "/incidents", null, hop.access_token)).status === 403);
check("no console/CSP errors (operator)", h.problems.length === 0);
await h.ctx.close();

// ---- dispatcher sees the response and withdraws -----------------------------------
const d2 = await signIn("dispatcher@raksha.example");
await d2.page.waitForURL("**/dashboard");
await d2.page.goto("http://localhost:3001/incidents/" + inc.body.id, { waitUntil: "networkidle" });
await d2.page.getByText("Acknowledged").first().waitFor({ timeout: 8000 });
check("dispatcher sees the hospital's acknowledgement", true);
await d2.page.getByRole("button", { name: /withdraw notice/i }).click();
await d2.page.getByRole("button", { name: "Confirm withdraw" }).click();
let cancelled;
for (let i = 0; i < 20; i++) {
  cancelled = await call("GET", `/incidents/${inc.body.id}/hospital-notices`, null, disp.access_token);
  if (cancelled.body[0]?.status === "CANCELLED") break;
  await d2.page.waitForTimeout(250);
}
check("withdrawn notice is CANCELLED server-side", cancelled.body[0].status === "CANCELLED");
await d2.ctx.close();

// ---- mobile ---------------------------------------------------------------------------
const m = await signIn("dispatcher@raksha.example", 390, 844);
await m.page.waitForURL("**/dashboard");
await m.page.goto("http://localhost:3001/hospitals", { waitUntil: "networkidle" });
await m.page.waitForTimeout(1200);
check("mobile: hospitals has no horizontal overflow", !(await m.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));
await m.page.screenshot({ path: `${SHOT}/hosp-4-mobile.png`, fullPage: true });
await browser.close();
console.log(out.join("\n"));
