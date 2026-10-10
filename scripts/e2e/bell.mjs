// Browser check against a RUNNING stack (API :8000 seeded dev data; apps :3000/:3001/:3002 built).
// Needs playwright-core (not a repository dependency) and Chromium (CHROMIUM_PATH). Not part of check.sh.
// Creates incidents/resources in the dev DB. Prints PASS/FAIL per check.
import { chromium } from "playwright-core";
const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e) => (await call("POST", "/auth/login", { email: e, password: PW })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const disp = await login("dispatcher@raksha.example"), resp = await login("responder@raksha.example"), cit = await login("citizen@raksha.example");
const tag = Date.now().toString(36).slice(-4).toUpperCase();
const unit = await call("POST", "/resources", { call_sign: "BEL-" + tag, name: "Bell Ambulance", resource_type: "AMBULANCE", latitude: 13.085, longitude: 80.27, operator_id: resp.user.id }, disp.access_token);
const inc = await call("POST", "/incidents", { category: "MEDICAL", description: "Collapsed pedestrian, not responding (bell e2e " + tag + ")", latitude: 13.0827, longitude: 80.2707, medical_required: true, immediate_danger: true }, cit.access_token);
const before = await call("GET", "/notifications/unread-count", null, resp.access_token);
const d = await call("POST", `/incidents/${inc.body.id}/dispatches`, { resource_id: unit.body.id }, disp.access_token);
check("dispatch created", d.status === 201);
const after = await call("GET", "/notifications/unread-count", null, resp.access_token);
check(`responder unread count rose (${before.body.unread} -> ${after.body.unread})`, after.body.unread > before.body.unread);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const page = await (await browser.newContext({ viewport: { width: 420, height: 900 } })).newPage();
const problems = []; page.on("console", (m) => { if (/content security policy|refused to/i.test(m.text())) problems.push(m.text().slice(0, 160)); });
await page.goto("http://localhost:3002/login", { waitUntil: "networkidle" });
await page.fill('input[name="email"]', "responder@raksha.example"); await page.fill('input[name="password"]', PW);
await page.click('button[type="submit"]'); await page.waitForTimeout(2500);
const bell = page.getByRole("button", { name: /^Notifications/ });
const label = await bell.getAttribute("aria-label");
check(`responder bell shows unread (${label})`, /\d+ unread/.test(label) && !/none/.test(label));
await bell.click();
await page.getByRole("region", { name: "Notifications" }).getByText("Assignment").first().waitFor();
const text = (await page.getByRole("region", { name: "Notifications" }).innerText()).replace(/\s+/g, " ");
check("assignment notification listed", /Assignment/.test(text));
check("no false claim of SMS/email delivery (this kind records in-app only)", !/sms|email/i.test(text));
await page.screenshot({ path: `${process.env.SHOT_DIR ?? "."}/bell-responder.png` });
await page.getByRole("region", { name: "Notifications" }).getByRole("button").filter({ hasText: /Assignment/ }).first().click();
await page.waitForURL(/\/assignments\//, { timeout: 8000 });
check("click opens the assignment", /\/assignments\/[0-9a-f-]+/.test(page.url()));
await page.waitForTimeout(800);
const after2 = await call("GET", "/notifications/unread-count", null, resp.access_token);
check(`reading it lowered the server-side count (${after.body.unread} -> ${after2.body.unread})`, after2.body.unread === after.body.unread - 1);
// Someone else's notification must not be readable: dispatcher token on responder's notification
const list = await call("GET", "/notifications?page_size=1", null, resp.access_token);
const other = await call("POST", `/notifications/${list.body.items[0].id}/read`, null, cit.access_token);
check("another user cannot mark it read (404)", other.status === 404);
check("no CSP violations", problems.length === 0);
await browser.close();
console.log(out.join("\n"));
