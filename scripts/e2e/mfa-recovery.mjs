// Browser check: MFA recovery codes, end to end, including the case that motivated them -
// an administrator (whom nobody else can reset) who has lost their authenticator.
// Needs a RUNNING stack (API :8000 seeded dev data, built control centre :3001 and responder
// app :3002), playwright-core (not a repository dependency) and Chromium (CHROMIUM_PATH).
// Not part of check.sh. Creates users in the dev DB.
import crypto from "node:crypto";
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", CC = "http://localhost:3001", RESP = "http://localhost:3002", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";

function b32decode(s) { const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const c of s.replace(/[=\s]+/g, "")) bits += A.indexOf(c).toString(2).padStart(5, "0"); const b = []; for (let i = 0; i + 8 <= bits.length; i += 8) b.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(b); }
function totp(secret) { const step = Math.floor(Date.now() / 1000 / 30); const m = Buffer.alloc(8); m.writeBigUInt64BE(BigInt(step)); const h = crypto.createHmac("sha1", b32decode(secret)).update(m).digest(); const o = h[19] & 0xf; return String((((h[o] & 0x7f) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3]) % 1_000_000).padStart(6, "0"); }
let lastStep = 0;
async function freshCode(secret) { for (;;) { const s = Math.floor(Date.now() / 1000 / 30); if (s > lastStep) { lastStep = s; return totp(secret); } await new Promise((r) => setTimeout(r, 1000)); } }

const tag = Date.now().toString(36).slice(-5);
const admin = (await call("POST", "/auth/login", { email: "admin@raksha.example", password: PW })).body;
const settled = "settled-passphrase-" + tag;
async function newUser(label, role) {
  const email = `rc-${label}-${tag}@example.com`, initial = "e2e-initial-passphrase-" + tag;
  const made = (await call("POST", "/users", { email, full_name: `RC ${label} ${tag}`, password: initial, role }, admin.access_token)).body;
  const first = (await call("POST", "/auth/login", { email, password: initial })).body;
  await call("POST", "/auth/password", { current_password: initial, new_password: settled }, first.access_token);
  return { id: made.id, email };
}
const bearer = async (email, code) => (await call("POST", "/auth/login", { email, password: settled, ...(code ? { mfa_code: code } : {}) })).body;
const remaining = async (token) => (await call("GET", "/auth/mfa/recovery-codes", null, token)).body.remaining;

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const problems = [];
async function page(w = 1280, h = 1000) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const p = await ctx.newPage();
  p.on("console", (m) => { if (/content security policy|refused to|error/i.test(m.text()) && !/Failed to load resource|tile\.openstreetmap|ERR_/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
  p.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
  return { ctx, p };
}
async function signIn(p, base, email, code) {
  await p.goto(`${base}/login`, { waitUntil: "networkidle" });
  await p.fill('input[name="email"]', email); await p.fill('input[name="password"]', settled);
  await p.click('button[type="submit"]');
  if (code !== undefined) { await p.waitForSelector('input[name="mfa_code"]'); await p.fill('input[name="mfa_code"]', code); await p.click('button[type="submit"]'); }
}

// ---- an administrator enrols in the control centre -------------------------------------------
const lone = await newUser("admin", "ADMIN");
const a = await page();
await signIn(a.p, CC, lone.email);
await a.p.waitForURL("**/dashboard", { timeout: 15000 });
await a.p.goto(`${CC}/account/security`, { waitUntil: "networkidle" });
await a.p.getByRole("button", { name: "Set up two-factor" }).click();
const key = (await a.p.getByLabel("Setup key").innerText()).replace(/\s+/g, "");
await a.p.getByLabel(/Code from the app/).fill(await freshCode(key));
await a.p.getByRole("button", { name: "Turn on" }).click();
const group = a.p.getByRole("group", { name: "Recovery codes", exact: true });
await group.waitFor({ timeout: 8000 });
const codes = (await group.getByRole("listitem").allInnerTexts()).map((t) => t.trim());
check("ten recovery codes are shown after turning it on", codes.length === 10 && codes.every((c) => /^[A-Z]{4}-[A-Z]{4}-[A-Z]{4}$/.test(c)));
check("the screen says they are not shown again", /not shown again/i.test(await group.innerText()));
check("Done stays disabled until they are marked saved", await group.getByRole("button", { name: "Done" }).isDisabled());
await a.p.screenshot({ path: `${SHOT}/recovery-codes.png`, fullPage: true });
await group.getByRole("checkbox").check();
await group.getByRole("button", { name: "Done" }).click();
check("…then the codes are gone from the page", !(await a.p.locator("body").innerText()).includes(codes[0]));
check("the screen counts ten unused", await a.p.getByText("10 unused recovery codes.").waitFor({ timeout: 8000 }).then(() => true, () => false));
const adminAccess = (await bearer(lone.email, await freshCode(key))).access_token;
check("the server agrees: ten left", (await remaining(adminAccess)) === 10);
await a.ctx.close();

// ---- the phone is lost: sign in with a recovery code --------------------------------------------
const b = await page();
await b.p.goto(`${CC}/login`, { waitUntil: "networkidle" });
await b.p.fill('input[name="email"]', lone.email); await b.p.fill('input[name="password"]', settled);
await b.p.click('button[type="submit"]');
await b.p.waitForSelector('input[name="mfa_code"]');
check("sign-in asks for a code or a recovery code", /recovery code/i.test(await b.p.locator("form").innerText()));
const loose = codes[0].toLowerCase().replace(/-/g, " ");
await b.p.fill('input[name="mfa_code"]', loose);
await b.p.click('button[type="submit"]');
await b.p.waitForURL("**/dashboard", { timeout: 15000 });
check("a recovery code typed loosely (lower case, spaces) signs the administrator in", true);

await b.p.goto(`${CC}/account/security`, { waitUntil: "networkidle" });
check("the count dropped to nine", await b.p.getByText("9 unused recovery codes.").waitFor({ timeout: 8000 }).then(() => true, () => false));

// the same code cannot be used again
const c = await page();
await signIn(c.p, CC, lone.email, codes[0]);
const refused = await c.p.getByRole("alert").filter({ hasText: /incorrect or has expired/i }).waitFor({ timeout: 8000 }).then(() => true, () => false);
check("the same code is refused the second time", refused);
check("…and the sign-in stays on the login page", new URL(c.p.url()).pathname.endsWith("/login"));
await c.ctx.close();

// ---- replace the set, then turn two-factor off with a recovery code (still no device) ------------
await b.p.getByRole("button", { name: /Get new recovery codes/ }).click();
const renew = b.p.getByRole("group", { name: "New recovery codes", exact: true });
await renew.getByLabel("Password").fill(settled);
await renew.getByLabel(/Current code or recovery code/).fill(codes[1]);
await renew.getByRole("button", { name: "Make new codes" }).click();
const fresh = b.p.getByRole("group", { name: "Recovery codes", exact: true });
await fresh.waitFor({ timeout: 8000 });
const newCodes = (await fresh.getByRole("listitem").allInnerTexts()).map((t) => t.trim());
check("new codes are shown and none match the old set", newCodes.length === 10 && !newCodes.some((x) => codes.includes(x)));
await fresh.getByRole("checkbox").check(); await fresh.getByRole("button", { name: "Done" }).click();
const oldTry = await call("POST", "/auth/login", { email: lone.email, password: settled, mfa_code: codes[2] });
check("an old, never-used code no longer works", oldTry.status === 401);

await b.p.getByRole("button", { name: /Turn off two-factor/ }).click();
const off = b.p.getByRole("group", { name: "Turn off two-factor", exact: true });
await off.getByLabel("Password").fill(settled);
await off.getByLabel(/Current code or recovery code/).fill(newCodes[0]);
await off.getByRole("button", { name: "Confirm turn off" }).click();
await b.p.getByRole("status").filter({ hasText: "is off" }).waitFor({ timeout: 8000 });
const me = (await call("GET", "/auth/me", null, (await bearer(lone.email)).access_token)).body;
check("two-factor is off, using only a recovery code (no device, no other administrator)", me.mfa_enabled === false);
check("no console/CSP errors in the control centre", problems.length === 0);
await b.ctx.close();

// ---- the other apps accept a recovery code at sign-in too -----------------------------------------------
const resp = await newUser("crew", "RESPONDER");
const rt = (await bearer(resp.email)).access_token;
const secret = (await call("POST", "/auth/mfa/enroll", null, rt)).body.secret;
const enabled = await call("POST", "/auth/mfa/enable", { code: await freshCode(secret) }, rt);
const crewCodes = enabled.body.recovery_codes;
const r = await page(420, 900);
await signIn(r.p, RESP, resp.email, crewCodes[0]);
await r.p.waitForURL("**/assignments", { timeout: 15000 });
check("the responder app signs a responder in with a recovery code", true);
await r.p.goto(`${RESP}/account/security`, { waitUntil: "networkidle" });
check("…and its security screen shows nine left", await r.p.getByText("9 unused recovery codes.").waitFor({ timeout: 8000 }).then(() => true, () => false));
check("responder app: no horizontal overflow", !(await r.p.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));
await r.p.screenshot({ path: `${SHOT}/recovery-responder.png`, fullPage: true });
await r.ctx.close();
await browser.close();

console.log(out.join("\n"));
process.exit(out.some((l) => l.startsWith("FAIL")) ? 1 : 0);
