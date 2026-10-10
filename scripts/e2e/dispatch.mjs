// Browser check of the control-centre dispatch workflow, against a RUNNING stack.
//
// NOT part of ./scripts/check.sh: it needs a live API (:8000, seeded dev data),
// the built control centre (:3001) and responder app (:3002), and `playwright-core`
// (not a repository dependency — install it in a scratch directory) plus the
// Chromium at CHROMIUM_PATH. It creates resources and an incident in the dev DB.
//
//   node dispatch.mjs        # prints PASS/FAIL per check; screenshots to SHOT_DIR
import { chromium } from "playwright-core";

const SHOT_DIR = process.env.SHOT_DIR ?? ".";
const API = "http://localhost:8000/api/v1";
const PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (method, path, body, token) =>
  fetch(API + path, { method, headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined }).then(j);
const login = async (email) => (await call("POST", "/auth/login", { email, password: PW })).body;

const out = [];
const check = (label, ok) => { out.push(`${ok ? "PASS" : "FAIL"}  ${label}`); };

const disp = await login("dispatcher@raksha.example");
const resp = await login("responder@raksha.example");
const cit = await login("citizen@raksha.example");

// Two ambulances near a point picked per run (so units left by earlier runs are not
// equally close), one about 0.7 km away and one about 5.7 km away.
const [BLAT, BLON] = [26 + Math.random() * 4, 74 + Math.random() * 6];
const near = (dLat, dLon) => [+(BLAT + dLat).toFixed(4), +(BLON + dLon).toFixed(4)];
const mk = (call_sign, name, resource_type, latitude, longitude, operator_id) =>
  call("POST", "/resources", { call_sign, name, resource_type, latitude, longitude, crew_size: 3, capabilities: ["als"], operator_id }, disp.access_token);
const tag = Date.now().toString(36).slice(-4).toUpperCase();
const a1 = await mk(`E2E-A1-${tag}`, "Ambulance One", "AMBULANCE", ...near(0.0061, 0.001), resp.user.id);
const a2 = await mk(`E2E-A2-${tag}`, "Ambulance Two", "AMBULANCE", ...near(0.0361, 0.041));
out.push(`resources created: ${a1.status}, ${a2.status}`);

const inc = await call("POST", "/incidents", {
  category: "MEDICAL", description: `Person collapsed in the market, not breathing normally (e2e ${tag})`,
  latitude: +BLAT.toFixed(4), longitude: +BLON.toFixed(4), people_affected: 1, medical_required: true, immediate_danger: true,
}, cit.access_token);
out.push(`incident created: ${inc.status} ${inc.body.reference_code}`);
const incId = inc.body.id;

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
const page = await ctx.newPage();
const problems = [];
page.on("console", (m) => { if (/content security policy|refused to|error/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));

await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await page.fill('input[name="email"]', "dispatcher@raksha.example");
await page.fill('input[name="password"]', PW);
await page.click('button[type="submit"]');
await page.waitForURL("**/dashboard", { timeout: 15000 });

await page.goto(`http://localhost:3001/incidents/${incId}`, { waitUntil: "networkidle" });
const panel = page.locator("section", { has: page.getByRole("heading", { name: "Dispatch", exact: true }) });
await panel.waitFor();
await page.getByRole("list", { name: "Suggested units" }).waitFor();
const text = (await panel.innerText()).replace(/\s+/g, " ");
check("nearest unit suggested; 5.7 km unit not offered while a closer one exists", /E2E-A1-/.test(text) && !text.includes(`E2E-A2-${tag}`));
check("ETA labelled as straight-line estimate", /straight-line estimate/.test(text));
check("reasons shown", (await panel.locator('ul[aria-label="Suggested units"] li ul li').count()) > 0);
check("no approver input", (await panel.getByLabel(/approv/i).count()) === 0);
await page.screenshot({ path: `${SHOT_DIR}/dispatch-1-recs.png`, fullPage: true });

// Step 1: choose. Nothing must exist yet.
// Choose this run's unit (earlier runs may have left equally close units behind).
await panel.getByRole("list", { name: "Suggested units" }).locator(":scope > li").filter({ hasText: `E2E-A1-${tag}` }).getByRole("button", { name: "Dispatch…" }).click();
check("confirmation step shown", await panel.getByText(/recorded as the approving dispatcher/i).isVisible());
let list = await call("GET", `/incidents/${incId}/dispatches`, null, disp.access_token);
check("no dispatch exists before confirming", Array.isArray(list.body) ? list.body.length === 0 : (list.body.items ?? []).length === 0);

// Step 2: confirm.
await panel.getByLabel(/note for the crew/i).fill("Enter by the north gate");
await panel.getByRole("button", { name: "Confirm dispatch" }).click();
await panel.getByRole("list", { name: "Dispatches" }).waitFor();
const after = (await panel.innerText()).replace(/\s+/g, " ");
check("dispatch listed with approver name", /Approved by .*Dispatcher|Approved by /.test(after));
check("note shown", /Enter by the north gate/.test(after));
list = await call("GET", `/incidents/${incId}/dispatches`, null, disp.access_token);
const rows = Array.isArray(list.body) ? list.body : list.body.items;
check("server recorded exactly one dispatch approved by the signed-in user", rows.length === 1 && rows[0].approved_by.id === disp.user.id);
const sent = rows[0].resource.call_sign;
const sugg = await page.getByRole("list", { name: "Suggested units" }).innerText().catch(() => "");
check(`dispatched unit (${sent}) no longer suggested`, !sugg.includes(sent));
await page.screenshot({ path: `${SHOT_DIR}/dispatch-2-dispatched.png`, fullPage: true });

// Responder sees it.
const mine = await call("GET", "/dispatches/mine", null, resp.access_token);
const assigned = (Array.isArray(mine.body) ? mine.body : mine.body.items ?? []).some((a) => a.id === rows[0].id);
check("responder's assignment list contains it (API)", assigned);
const rpage = await ctx.newPage();
await rpage.goto("http://localhost:3002/login", { waitUntil: "networkidle" });
await rpage.fill('input[name="email"]', "responder@raksha.example");
await rpage.fill('input[name="password"]', PW);
await rpage.click('button[type="submit"]');
await rpage.waitForTimeout(2500);
const rtext = (await rpage.locator("body").innerText()).replace(/\s+/g, " ");
check("responder app shows the assignment (incident reference)", rtext.includes(inc.body.reference_code));
await rpage.screenshot({ path: `${SHOT_DIR}/dispatch-3-responder.png`, fullPage: true });

// Stand down: reason mandatory.
await panel.getByRole("button", { name: "Stand down…" }).click();
check("stand-down disabled without a reason", await panel.getByRole("button", { name: "Confirm stand down" }).isDisabled());
await panel.getByLabel(/reason/i).fill("Reassigned to a larger incident");
await panel.getByRole("button", { name: "Confirm stand down" }).click();
await panel.getByText(/Stood down: Reassigned to a larger incident/).waitFor({ timeout: 8000 });
check("stand-down recorded with reason", true);
list = await call("GET", `/incidents/${incId}/dispatches`, null, disp.access_token);
const r2 = Array.isArray(list.body) ? list.body : list.body.items;
check("server shows CANCELLED + reason", r2[0].status === "CANCELLED" && r2[0].cancel_reason === "Reassigned to a larger incident");
await page.waitForSelector('ul[aria-label="Suggested units"]');
const again = (await panel.innerText()).replace(/\s+/g, " ");
check("freed unit is suggested again", again.includes(sent));
await page.screenshot({ path: `${SHOT_DIR}/dispatch-4-standdown.png`, fullPage: true });

// A non-dispatch operational view: responder token must be refused by the API.
const denied = await call("POST", `/incidents/${incId}/dispatches`, { resource_id: a2.body.id }, resp.access_token);
check("responder cannot dispatch via API (403)", denied.status === 403);

check("no CSP violations or console errors", problems.length === 0);
if (problems.length) out.push("  problems: " + problems.join(" | "));
await browser.close();
console.log(out.join("\n"));
