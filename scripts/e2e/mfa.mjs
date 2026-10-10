// Browser check: two-factor enrolment screen.
//
//   node mfa.mjs                 against an API started normally
//   MFA_ENFORCED=1 MFA_TEST_EMAIL=... MFA_TEST_PASSWORD=... node mfa.mjs
//                                against an API started with
//                                RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL=true. Under
//                                enforcement even an administrator cannot create
//                                users until enrolled, so create the dispatcher
//                                account first (without enforcement) and pass it in.
//
// Needs a RUNNING stack (API :8000 seeded dev data, built control centre :3001),
// playwright-core (not a repository dependency) and Chromium (CHROMIUM_PATH).
// Optional: QR_DECODER=/path/to/python-with-opencv to decode the QR image and
// compare it with the setup key. Not part of check.sh. Creates users in the dev DB.
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const ENFORCED = process.env.MFA_ENFORCED === "1";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";

function b32decode(s) { const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const c of s.replace(/=+$/, "")) bits += A.indexOf(c).toString(2).padStart(5, "0"); const b = []; for (let i = 0; i + 8 <= bits.length; i += 8) b.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(b); }
function totp(secret, off = 0) { const step = Math.floor(Date.now() / 1000 / 30) + off; const m = Buffer.alloc(8); m.writeBigUInt64BE(BigInt(step)); const h = crypto.createHmac("sha1", b32decode(secret)).update(m).digest(); const o = h[19] & 0xf; return String((((h[o] & 0x7f) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3]) % 1_000_000).padStart(6, "0"); }

// The server accepts a time step only once and only moving forward, and only
// within a small window, so each use needs a code from a step later than the last.
let lastStep = 0;
async function freshCode(secret) {
  for (;;) {
    const step = Math.floor(Date.now() / 1000 / 30);
    if (step > lastStep) { lastStep = step; return totp(secret); }
    await new Promise((r) => setTimeout(r, 1000));
  }
}

const tag = Date.now().toString(36).slice(-5);
let email, pw, adminLogin, made;
if (ENFORCED) {
  email = process.env.MFA_TEST_EMAIL; pw = process.env.MFA_TEST_PASSWORD;
  if (!email || !pw) { console.log("MFA_ENFORCED needs MFA_TEST_EMAIL and MFA_TEST_PASSWORD"); process.exit(2); }
  check("pre-created account is in the enforced state (API refuses its data)", (await call("GET", "/incidents", null, (await call("POST", "/auth/login", { email, password: pw })).body.access_token)).body.error?.code === "MFA_ENROLLMENT_REQUIRED");
} else {
  adminLogin = (await call("POST", "/auth/login", { email: "admin@raksha.example", password: PW })).body;
  email = `mfa-ui-${tag}@example.com`; pw = "e2e-initial-passphrase-" + tag;
  made = await call("POST", "/users", { email, full_name: `MFA UI ${tag}`, password: pw, role: "DISPATCHER" }, adminLogin.access_token);
  check("test account created", made.status === 201);
}

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
const page = await ctx.newPage(); const problems = [];
page.on("console", (m) => { if (/content security policy|refused to/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
async function uiLogin(code) {
  await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', email); await page.fill('input[name="password"]', pw);
  await page.click('button[type="submit"]');
  if (code) { await page.waitForSelector('input[name="mfa_code"]', { timeout: 10000 }); await page.fill('input[name="mfa_code"]', code); await page.click('button[type="submit"]'); }
}

await uiLogin();
if (ENFORCED) {
  await page.waitForURL("**/account/security", { timeout: 15000 });
  check("enforced: an unenrolled operator is sent to the security screen on their first refused call", /\/account\/security$/.test(page.url()));
} else {
  await page.waitForURL("**/dashboard", { timeout: 15000 });
  await page.getByRole("link", { name: "Security" }).click();
  await page.waitForURL("**/account/security");
}
const panel = page.getByRole("region", { name: "Two-factor authentication" });
await panel.waitFor();
check("shows Off before enrolment", /Off/.test(await panel.innerText()));
await panel.getByRole("button", { name: "Set up two-factor" }).click();
await panel.getByLabel("Setup key").waitFor();
const grouped = (await panel.getByLabel("Setup key").innerText()).trim();
const secret = grouped.replace(/\s+/g, "");
check("setup key is base32, 32 chars", /^[A-Z2-7]{32}$/.test(secret));
check("QR code drawn and warning about no backup codes shown", (await panel.getByRole("img", { name: /qr code/i }).count()) === 1 && /no backup codes/i.test(await panel.innerText()));
await panel.getByRole("img", { name: /qr code/i }).screenshot({ path: `${SHOT}/mfa-qr.png` });
if (process.env.QR_DECODER) {
  const decoded = execFileSync(process.env.QR_DECODER, ["-c", `import cv2,sys;img=cv2.imread(sys.argv[1]);img=cv2.copyMakeBorder(img,40,40,40,40,cv2.BORDER_CONSTANT,value=(255,255,255));t,_,_=cv2.QRCodeDetector().detectAndDecode(img);print(t)`, `${SHOT}/mfa-qr.png`]).toString().trim();
  check(`QR decodes to an otpauth URI carrying the same secret`, decoded.startsWith("otpauth://totp/") && decoded.includes("secret=" + secret));
}
check("nothing is enabled yet (login needs no code)", !!(await call("POST", "/auth/login", { email, password: pw })).body.access_token);
await panel.getByLabel(/Code from the app/).fill("000000");
await panel.getByRole("button", { name: "Turn on" }).click();
await panel.getByRole("alert").waitFor({ timeout: 8000 });
check("a wrong code is refused with the server's message and stays in setup", /incorrect|expired/i.test(await panel.getByRole("alert").innerText()) && (await panel.getByLabel("Setup key").count()) === 1);
await panel.getByLabel(/Code from the app/).fill(await freshCode(secret));
await panel.getByRole("button", { name: "Turn on" }).click();
await panel.getByRole("status").waitFor({ timeout: 8000 });
check("status flips to On", /● On/.test(await panel.innerText()));
if (!ENFORCED) {
  const me = await call("GET", `/users/${made.body.id}`, null, adminLogin.access_token);
  check("server agrees: mfa_enabled", me.body.mfa_enabled === true);
}
await page.screenshot({ path: `${SHOT}/mfa-on.png` });
if (ENFORCED) {
  await page.goto("http://localhost:3001/dashboard", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  check("enforced: after enrolling the console works (no bounce back to security)", /\/dashboard$/.test(page.url()));
}

// sign out, sign back in with a code
await page.getByRole("button", { name: "Sign out" }).click();
await page.waitForTimeout(800);
await uiLogin();
await page.waitForSelector('input[name="mfa_code"]', { timeout: 10000 });
check("sign-in now asks for a code", true);
await page.fill('input[name="mfa_code"]', await freshCode(secret));
await page.click('button[type="submit"]');
await page.waitForURL(/\/(dashboard|account\/security)$/, { timeout: 15000 });
check("signing in with a fresh code works", /\/(dashboard|account\/security)$/.test(page.url()));

// turn off
await page.goto("http://localhost:3001/account/security", { waitUntil: "networkidle" });
await panel.getByRole("button", { name: /Turn off two-factor/ }).click();
await panel.getByLabel("Password").fill("wrong-password-wrong");
await panel.getByLabel("Current code").fill(await freshCode(secret));
await panel.getByRole("button", { name: "Confirm turn off" }).click();
await panel.getByRole("alert").waitFor({ timeout: 8000 });
check("turning off with a wrong password is refused and MFA stays on", (await call("POST", "/auth/login", { email, password: pw })).body.error?.code === "MFA_REQUIRED");
await panel.getByLabel("Password").fill(pw);
await panel.getByLabel("Current code").fill(await freshCode(secret));
await panel.getByRole("button", { name: "Confirm turn off" }).click();
await panel.getByRole("status").waitFor({ timeout: 8000 });
check("turned off with password + code; login needs no code again", !!(await call("POST", "/auth/login", { email, password: pw })).body.access_token || ENFORCED);
check("no console/CSP errors", problems.length === 0);
if (problems.length) out.push("   " + problems.join(" | "));
await browser.close();
console.log(out.join("\n"));
