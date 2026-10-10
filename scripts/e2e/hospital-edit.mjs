// Browser check: administrators correct a hospital's details, relink its operator, and retire / restore it.
// Needs a RUNNING stack (API :8000 seeded dev data, built control centre :3001), playwright-core
// (not a repository dependency) and Chromium (CHROMIUM_PATH). Not part of check.sh.
// Creates users, a hospital, an incident and a notice in the dev DB.
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", APP = "http://localhost:3001", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e) => (await call("POST", "/auth/login", { email: e, password: PW })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const poll = async (fn, ok, tries = 20) => { for (let i = 0; i < tries; i++) { const r = await fn(); if (ok(r)) return r; await sleep(300); } return fn(); };

const tag = Date.now().toString(36).slice(-5).toUpperCase();
const admin = await login("admin@raksha.example"), disp = await login("dispatcher@raksha.example"), cit = await login("citizen@raksha.example");
const settled = "settled-passphrase-" + tag;
// An administrator-set password must be replaced before the account can act, so settle each operator.
const mkOp = async (n) => {
  const email = `hop${n}-${tag.toLowerCase()}@example.com`, initial = "e2e-initial-passphrase-" + tag;
  const made = (await call("POST", "/users", { email, full_name: `Operator ${n} ${tag}`, password: initial, role: "HOSPITAL_OPERATOR" }, admin.access_token)).body;
  const first = (await call("POST", "/auth/login", { email, password: initial })).body;
  await call("POST", "/auth/password", { current_password: initial, new_password: settled }, first.access_token);
  const token = async () => (await call("POST", "/auth/login", { email, password: settled })).body.access_token;
  return { ...made, token };
};
const op1 = await mkOp("one"), op2 = await mkOp("two");
const made = await call("POST", "/hospitals", { code: "E2E-" + tag, name: "Edit Test Hospital " + tag, latitude: 13.05, longitude: 80.25, total_beds: 40, available_beds: 10, icu_total: 6, icu_available: 2, contact_phone: "+91 44 0000 1111", managed_by_id: op1.id }, admin.access_token);
check("hospital registered for the test", made.status === 201);
const id = made.body.id;
const get = async () => (await call("GET", `/hospitals/${id}`, null, admin.access_token)).body;

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
async function open(email, w = 1440, h = 1000) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage(); const problems = [];
  page.on("console", (m) => { if (/content security policy|refused to|error/i.test(m.text()) && !/tile\.openstreetmap|Failed to load resource|ERR_/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
  await page.goto(`${APP}/login`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', email); await page.fill('input[name="password"]', PW);
  await page.click('button[type="submit"]'); await page.waitForURL(/\/(dashboard|hospitals)$/, { timeout: 15000 });
  await page.goto(`${APP}/hospitals`, { waitUntil: "networkidle" });
  return { ctx, page, problems };
}
const select = async (page) => { await page.getByPlaceholder("Search name or code").fill(tag); await page.getByRole("button", { name: new RegExp("Edit Test Hospital " + tag) }).first().click(); await page.getByRole("region", { name: "Hospital detail" }).waitFor(); };

// ---- a dispatcher cannot edit ----------------------------------------------------------
{
  const d = await open("dispatcher@raksha.example");
  await select(d.page);
  check("a dispatcher sees no Edit details button", (await d.page.getByRole("button", { name: "Edit details" }).count()) === 0);
  check("…and the API refuses them (403)", (await call("PATCH", `/hospitals/${id}`, { name: "No" }, disp.access_token)).status === 403);
  await d.ctx.close();
}

// ---- an administrator corrects details ------------------------------------------------------
const a = await open("admin@raksha.example");
await select(a.page);
const detail = a.page.getByRole("region", { name: "Hospital detail" });
await detail.getByRole("button", { name: "Edit details" }).click();
const form = detail.getByRole("form", { name: "Edit hospital details" });
await form.waitFor();
check("the code is shown as fixed and beds are not editable here", /cannot be changed/.test(await form.innerText()) && (await form.getByLabel(/beds/i).count()) === 0);
await form.getByRole("button", { name: "Save changes" }).click();
check("saving without a change says so", await form.getByText("Nothing has changed.").isVisible());

await form.getByLabel(/^Name/).fill("Renamed Hospital " + tag);
await form.getByLabel("Contact phone").fill("+91 44 2222 3333");
await form.getByLabel("Address").fill("1 Test Road, Chennai");
await form.getByLabel("Latitude").fill("13.0600");
await form.getByLabel("Longitude").fill("80.2600");
await form.getByRole("button", { name: "Save changes" }).click();
const saved = await poll(get, (h) => h.name === "Renamed Hospital " + tag);
check("name saved (server agrees)", saved.name === "Renamed Hospital " + tag);
check("phone and address saved", saved.contact_phone === "+91 44 2222 3333" && saved.address === "1 Test Road, Chennai");
check("position moved", Number(saved.latitude) === 13.06 && Number(saved.longitude) === 80.26);
check("capacity untouched", saved.available_beds === 10 && saved.icu_total === 6);
check("the edit form closed and the card shows the new name", await a.page.getByRole("heading", { name: "Renamed Hospital " + tag }).first().isVisible());

// ---- relink the operator -----------------------------------------------------------------------
await detail.getByRole("button", { name: "Edit details" }).click();
await form.getByLabel("Hospital operator").selectOption(op2.id);
await form.getByRole("button", { name: "Save changes" }).click();
const relinked = await poll(get, (h) => h.managed_by?.id === op2.id);
check("operator changed to the other account", relinked.managed_by?.id === op2.id);
check("the previous operator can no longer report its capacity (403)", (await call("POST", `/hospitals/${id}/capacity`, { available_beds: 1 }, await op1.token())).status === 403);

// ---- retire: refused while a notice is open -----------------------------------------------------
const inc = (await call("POST", "/incidents", { category: "FIRE", description: "Hospital edit e2e " + tag, latitude: 13.06, longitude: 80.26, people_affected: 2 }, cit.access_token)).body;
const notice = (await call("POST", `/incidents/${inc.id}/hospital-notices`, { hospital_id: id, patient_count: 2, severity: "HIGH", eta_minutes: 9, clinical_notes: "e2e" }, disp.access_token)).body;
await detail.getByRole("button", { name: "Edit details" }).click();
await form.getByRole("button", { name: /Retire this hospital/ }).click();
await form.getByRole("button", { name: "Confirm retire" }).click();
await form.getByRole("alert").waitFor({ timeout: 8000 });
check("retiring with an open notice is refused, with the reason shown", /open inbound-patient notices/.test(await form.getByRole("alert").innerText()));
check("…and the hospital is still active", (await get()).is_active === true);
await a.page.screenshot({ path: `${SHOT}/hospital-edit-refused.png` });

// close the notice, as the hospital's (new) operator would, then retire
const closed = await call("POST", `/hospital-notices/${notice.id}/status`, { status: "DIVERTED", response_note: "Closing for e2e." }, await op2.token());
check("the operator closes the notice", closed.status === 200);
await form.getByRole("button", { name: /Retire this hospital/ }).click();
await form.getByRole("button", { name: "Confirm retire" }).click();
const retired = await poll(get, (h) => h.is_active === false);
check("retired once the notice is closed", retired.is_active === false);
await a.page.waitForTimeout(1200);
check("it leaves the default hospital list", (await a.page.getByRole("button", { name: new RegExp("Renamed Hospital " + tag) }).count()) === 0);

// ---- restore -------------------------------------------------------------------------------------------
await a.page.getByLabel("Include retired hospitals").check();
await select(a.page).catch(async () => { await a.page.getByPlaceholder("Search name or code").fill(tag); await a.page.getByRole("button", { name: /Renamed Hospital/ }).first().click(); });
check("a retired hospital is marked Retired in the detail", await detail.getByText("Retired").isVisible());
await detail.getByRole("button", { name: "Edit details" }).click();
await form.getByRole("button", { name: "Restore this hospital" }).click();
const back = await poll(get, (h) => h.is_active === true);
check("restored", back.is_active === true);
check("no console/CSP errors", a.problems.length === 0);
await a.ctx.close();

// ---- phone width ------------------------------------------------------------------------------------------
const m = await open("admin@raksha.example", 390, 844);
await select(m.page).catch(async () => { await m.page.getByPlaceholder("Search name or code").fill(tag); await m.page.getByRole("button", { name: /Renamed Hospital/ }).first().click(); });
await m.page.getByRole("button", { name: "Edit details" }).click();
await m.page.getByRole("form", { name: "Edit hospital details" }).waitFor();
check("mobile: no horizontal overflow", !(await m.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));
await m.page.screenshot({ path: `${SHOT}/hospital-edit-mobile.png`, fullPage: true });
await m.ctx.close();
await browser.close();

console.log(out.join("\n"));
process.exit(out.some((l) => l.startsWith("FAIL")) ? 1 : 0);
