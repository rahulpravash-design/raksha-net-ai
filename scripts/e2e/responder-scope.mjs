// Browser + API check: a responder reads assignments, not incident records.
// Needs a RUNNING stack (API :8000 seeded dev data, built control centre :3001),
// playwright-core (not a repository dependency) and Chromium (CHROMIUM_PATH).
// Not part of check.sh. Creates one incident in the dev DB.
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e) => (await call("POST", "/auth/login", { email: e, password: PW })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);

const cit = await login("citizen@raksha.example");
const resp = await login("responder@raksha.example");
const disp = await login("dispatcher@raksha.example");
const tag = Date.now().toString(36).slice(-4).toUpperCase();
const inc = await call("POST", "/incidents", { category: "FIRE", description: "Responder-scope e2e " + tag, latitude: 13.09, longitude: 80.28, people_affected: 1 }, cit.access_token);
const id = inc.body.id;

// ---- the API -------------------------------------------------------------------
const t = resp.access_token;
check("responder is refused the incident queue (403)", (await call("GET", "/incidents", null, t)).status === 403);
for (const suffix of ["", "/history", "/media", "/analyses", "/dispatches", "/hospital-notices", "/resource-recommendations"]) {
  const r = await call("GET", `/incidents/${id}${suffix}`, null, t);
  check(`responder cannot read /incidents/{id}${suffix} (${r.status})`, [403, 404].includes(r.status) && !JSON.stringify(r.body).includes(tag));
}
check("responder is refused the map feed (403)", (await call("GET", "/geo/incidents/bbox?min_lat=12&min_lon=79&max_lat=14&max_lon=81", null, t)).status === 403);
check("responder still reads own assignments (200)", (await call("GET", "/dispatches/mine", null, t)).status === 200);
check("dispatcher still reads the incident (200)", (await call("GET", `/incidents/${id}`, null, disp.access_token)).status === 200);
const assignToResponder = await call("POST", `/incidents/${id}/assign`, { assigned_to_id: resp.user.id }, disp.access_token);
check("an incident cannot be assigned to a responder (400)", assignToResponder.status === 400);

// ---- the control centre ----------------------------------------------------------
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await page.fill('input[name="email"]', "responder@raksha.example"); await page.fill('input[name="password"]', PW);
await page.click('button[type="submit"]'); await page.waitForTimeout(2500);
const body = (await page.locator("body").innerText()).replace(/\s+/g, " ");
check("control centre keeps a responder on the login page", new URL(page.url()).pathname === "/login");
check("…and points them to the responder app", /responder app/i.test(body));
const held = await page.evaluate(() => sessionStorage.getItem("raksha.access_token") || localStorage.getItem("raksha.access_token"));
check("…and leaves no session behind", !held);
await page.goto("http://localhost:3001/dashboard", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
check("the dashboard is not reachable afterwards", new URL(page.url()).pathname === "/login");

// a dispatcher is unaffected
await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await page.fill('input[name="email"]', "dispatcher@raksha.example"); await page.fill('input[name="password"]', PW);
await page.click('button[type="submit"]'); await page.waitForURL("**/dashboard", { timeout: 15000 });
check("a dispatcher still reaches the dashboard", true);
await browser.close();

console.log(out.join("\n"));
process.exit(out.some((l) => l.startsWith("FAIL")) ? 1 : 0);
