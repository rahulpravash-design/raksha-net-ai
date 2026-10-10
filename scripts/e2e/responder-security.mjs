// Browser check: a responder (and a citizen) can set their own password and two-factor.
//
// Why it matters: responders are operational, so a deployment that enforces two-factor
// (RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL=true) refuses everything for one who has not
// enrolled. Before this screen existed the responder app had no way to enrol — the
// account was locked out of its own application.
//
// Needs a RUNNING stack (API :8000 seeded dev data, built citizen app :3000 and responder
// app :3002), playwright-core (not a repository dependency) and Chromium (CHROMIUM_PATH).
// Not part of check.sh. Creates one responder in the dev DB.
import crypto from "node:crypto";
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", RESP = "http://localhost:3002", CIT = "http://localhost:3000", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";

function b32decode(s) { const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const c of s.replace(/[=\s]+/g, "")) bits += A.indexOf(c).toString(2).padStart(5, "0"); const b = []; for (let i = 0; i + 8 <= bits.length; i += 8) b.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(b); }
function totp(secret) { const step = Math.floor(Date.now() / 1000 / 30); const m = Buffer.alloc(8); m.writeBigUInt64BE(BigInt(step)); const h = crypto.createHmac("sha1", b32decode(secret)).update(m).digest(); const o = h[19] & 0xf; return String((((h[o] & 0x7f) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3]) % 1_000_000).padStart(6, "0"); }
// The server accepts a time step once, moving forward: wait for a later step each time.
let lastStep = 0;
async function freshCode(secret) { for (;;) { const s = Math.floor(Date.now() / 1000 / 30); if (s > lastStep) { lastStep = s; return totp(secret); } await new Promise((r) => setTimeout(r, 1000)); } }

const tag = Date.now().toString(36).slice(-5);
const email = `resp-sec-${tag}@example.com`, initial = "e2e-initial-passphrase-" + tag, mine = "my-own-passphrase-" + tag;
const admin = (await call("POST", "/auth/login", { email: "admin@raksha.example", password: PW })).body;
const made = await call("POST", "/users", { email, full_name: `Crew ${tag}`, password: initial, role: "RESPONDER" }, admin.access_token);
check("responder account created by an administrator", made.status === 201);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 420, height: 900 } });
const page = await ctx.newPage(); const problems = [];
page.on("console", (m) => { if (/content security policy|refused to|error/i.test(m.text()) && !/Failed to load resource/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
const signIn = async (password, code) => {
  await page.goto(`${RESP}/login`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', email); await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');
  if (code) { await page.waitForSelector('input[name="mfa_code"]'); await page.fill('input[name="mfa_code"]', code); await page.click('button[type="submit"]'); }
};

// ---- an administrator-set password must be replaced first ------------------------
await signIn(initial);
await page.waitForURL("**/account/security", { timeout: 15000 });
check("a freshly created responder is sent to the security screen", true);
const body = async () => (await page.locator("body").innerText()).replace(/\s+/g, " ");
check("it explains that an administrator set the password", /administrator set your password/i.test(await body()));
await page.getByLabel(/^Current password/).fill(initial);
await page.getByLabel(/^New password/).fill(mine);
await page.getByLabel(/^Repeat the new password/).fill(mine);
await page.getByRole("button", { name: /change password/i }).click();
await page.waitForURL("**/assignments", { timeout: 15000 });
check("changing it carries the responder on to their assignments", true);

// ---- turn two-factor on ----------------------------------------------------------------
await page.getByRole("link", { name: "Security" }).click(); await page.waitForURL("**/account/security");
await page.getByRole("button", { name: "Set up two-factor" }).click();
const key = (await page.getByLabel("Setup key").innerText()).replace(/\s+/g, "");
check("a QR code and a typed key are shown", (await page.getByRole("img", { name: /QR code/ }).count()) === 1 && /^[A-Z2-7]{16,}$/.test(key));
await page.getByLabel(/Code from the app/).fill("000000");
await page.getByRole("button", { name: "Turn on" }).click();
await page.getByRole("alert").waitFor({ timeout: 5000 });
check("a wrong code is refused and two-factor stays off", (await call("GET", `/users/${made.body.id}`, null, admin.access_token)).body.mfa_enabled === false);
await page.getByLabel(/Code from the app/).fill(await freshCode(key));
await page.getByRole("button", { name: "Turn on" }).click();
await page.getByRole("status").filter({ hasText: /Two-factor authentication is on/ }).waitFor({ timeout: 8000 });
check("the right code turns it on (server agrees)", (await call("GET", `/users/${made.body.id}`, null, admin.access_token)).body.mfa_enabled === true);
await page.screenshot({ path: `${SHOT}/responder-security.png`, fullPage: true });
check("no horizontal overflow at phone width", !(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));

// ---- sign-in now asks for the code ----------------------------------------------------------
await page.getByRole("button", { name: "Sign out" }).click(); await page.waitForTimeout(800);
await signIn(mine);
await page.waitForSelector('input[name="mfa_code"]');
check("sign-in asks for a verification code", true);
await page.fill('input[name="mfa_code"]', await freshCode(key));
await page.click('button[type="submit"]');
await page.waitForURL("**/assignments", { timeout: 15000 });
check("the code completes sign-in", true);

// ---- turn it off (password + current code) ------------------------------------------------------
await page.getByRole("link", { name: "Security" }).click(); await page.waitForURL("**/account/security");
await page.getByRole("button", { name: /Turn off two-factor/ }).click();
const off = page.getByRole("group", { name: "Turn off two-factor" });
await off.getByLabel("Password").fill(mine);
await off.getByLabel("Current code").fill(await freshCode(key));
await off.getByRole("button", { name: "Confirm turn off" }).click();
await page.getByRole("status").filter({ hasText: /is off/ }).waitFor({ timeout: 8000 });
check("it can be turned off with the password and a current code", (await call("GET", `/users/${made.body.id}`, null, admin.access_token)).body.mfa_enabled === false);
check("no console/CSP errors in the responder app", problems.length === 0);
await ctx.close();

// ---- a citizen has the same screen -------------------------------------------------------------------
const cctx = await browser.newContext({ viewport: { width: 420, height: 900 } });
const cpage = await cctx.newPage();
await cpage.goto(`${CIT}/login`, { waitUntil: "networkidle" });
await cpage.fill('input[name="email"]', "citizen@raksha.example"); await cpage.fill('input[name="password"]', PW);
await cpage.click('button[type="submit"]'); await cpage.waitForTimeout(2500);
await cpage.getByRole("link", { name: "Security" }).click(); await cpage.waitForURL("**/account/security");
check("a citizen reaches the same screen from the header", (await cpage.getByRole("region", { name: "Two-factor authentication" }).count()) === 1 && (await cpage.getByRole("region", { name: "Password" }).count()) === 1);
await cctx.close();
await browser.close();

console.log(out.join("\n"));
process.exit(out.some((l) => l.startsWith("FAIL")) ? 1 : 0);
