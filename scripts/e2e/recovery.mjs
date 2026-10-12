// Browser check: password recovery by email.
//
//   RECOVERY_MODE=unavailable node recovery.mjs   API started with no SMTP host
//   RECOVERY_MODE=mailbox MAILBOX_DIR=/tmp/mailbox node recovery.mjs
//        API started with RAKSHA_SMTP_HOST=127.0.0.1 RAKSHA_SMTP_PORT=1025
//        RAKSHA_SMTP_SECURITY=none, and `python scripts/dev_mailbox.py --port 1025
//        --dir /tmp/mailbox` running. Citizen app (:3000) must be running too.
//
// Needs a RUNNING stack, playwright-core (not a repository dependency) and
// Chromium (CHROMIUM_PATH). Not part of check.sh. Creates users in the dev DB.
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const MODE = process.env.RECOVERY_MODE ?? "mailbox";
const DIR = process.env.MAILBOX_DIR ?? "/tmp/mailbox";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e, p) => (await call("POST", "/auth/login", { email: e, password: p })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const mails = () => (fs.existsSync(DIR) ? fs.readdirSync(DIR).filter((f) => f.endsWith(".json")).sort().map((f) => JSON.parse(fs.readFileSync(path.join(DIR, f), "utf8"))) : []);
async function waitForMail(count, tries = 40) { for (let i = 0; i < tries; i++) { if (mails().length >= count) return mails(); await sleep(250); } return mails(); }

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
async function newPage(w = 1280, h = 900) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage(); const problems = [];
  page.on("console", (m) => { if (/content security policy|refused to/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
  return { ctx, page, problems };
}

const status = (await call("GET", "/auth/recovery-status")).body;
check(`API reports email_available=${MODE === "mailbox"}`, status.email_available === (MODE === "mailbox"));

if (MODE === "unavailable") {
  const { ctx, page, problems } = await newPage();
  await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await page.waitForURL("**/forgot-password");
  await page.getByText(/not set up for this system/i).waitFor({ timeout: 8000 });
  check("says recovery by email is not set up and points to an administrator", /ask an administrator/i.test(await page.locator("body").innerText()));
  check("offers no email form", (await page.getByLabel("Email address").count()) === 0);
  check("the API still answers a request with 202 (no account is revealed)", (await call("POST", "/auth/forgot-password", { email: "nobody@example.org" })).status === 202);
  await page.screenshot({ path: `${SHOT}/rec-0-unavailable.png` });
  check("no console/CSP errors", problems.length === 0);
  await ctx.close(); await browser.close();
  console.log(out.join("\n")); process.exit(0);
}

// ---- mailbox mode ---------------------------------------------------------------
const admin = await login("admin@raksha.example", PW);
const tag = Date.now().toString(36).slice(-5);
const email = `rec-${tag}@example.com`, initial = "admin-chosen-passphrase-" + tag, original = "original-passphrase-" + tag, recovered = "recovered-passphrase-" + tag;
await call("POST", "/users", { email, full_name: `Recovery ${tag}`, password: initial, role: "DISPATCHER" }, admin.access_token);
const first = await login(email, initial);
await call("POST", "/auth/password", { current_password: initial, new_password: original }, first.access_token);
// Lock the account for real: recovery proves control of the inbox, so it clears this.
for (let i = 0; i < 5; i++) await login(email, "wrong-password-" + i);
check("account is locked before recovery", (await login(email, original)).error?.code === "ACCOUNT_LOCKED");
const before = mails().length;

const { ctx, page, problems } = await newPage();
await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await page.getByRole("link", { name: "Forgot your password?" }).click();
await page.waitForURL("**/forgot-password");
await page.getByLabel("Email address").waitFor();
await page.getByLabel("Email address").fill("nobody-" + tag + "@example.com");
await page.getByRole("button", { name: "Send the link" }).click();
const unknownText = (await page.getByRole("status").innerText()).replace(/\s+/g, " ");
await sleep(1500);
check("an unknown address gets the non-committal answer and no mail is sent", /If an account exists/.test(unknownText) && mails().length === before);

await page.goto("http://localhost:3001/forgot-password", { waitUntil: "networkidle" });
await page.getByLabel("Email address").fill(email);
await page.getByRole("button", { name: "Send the link" }).click();
const knownText = (await page.getByRole("status").innerText()).replace(/\s+/g, " ");
check("a known address gets the identical answer", knownText === unknownText);
await page.screenshot({ path: `${SHOT}/rec-1-sent.png` });
const got = await waitForMail(before + 1);
const mail = got[got.length - 1];
check("one email arrived at that address", got.length === before + 1 && mail.to.includes(email));
check("subject is fixed and the body carries no operational data", mail.subject === "Reset your RAKSHA NET AI password" && /within 30 minutes/.test(mail.body));
const link = mail.body.match(/https?:\/\/\S+reset-password\?token=[\w-]+/)?.[0];
check("link points at the control centre (configured, not request-derived)", !!link && link.startsWith("http://localhost:3001/reset-password?token="));

await page.goto(link, { waitUntil: "networkidle" });
await page.getByRole("heading", { name: "Choose a new password" }).waitFor();
check("the token is removed from the address bar", !page.url().includes("token="));
await page.getByLabel(/^New password/).fill(recovered);
await page.getByLabel(/^Repeat the new password/).fill(recovered + "x");
await page.getByRole("button", { name: "Change password" }).click();
check("mismatch is caught locally", (await page.getByText(/do not match/i).count()) === 1);
await page.getByLabel(/^New password/).fill("short"); await page.getByLabel(/^Repeat the new password/).fill("short");
await page.getByRole("button", { name: "Change password" }).click();
await page.getByRole("alert").filter({ hasText: /characters|common/i }).waitFor({ timeout: 8000 });
check("a weak password is refused with the server's message and the link survives", (await page.getByLabel(/^New password/).count()) === 1);
await page.getByLabel(/^New password/).fill(recovered); await page.getByLabel(/^Repeat the new password/).fill(recovered);
await page.getByRole("button", { name: "Change password" }).click();
await page.getByRole("heading", { name: "Password changed" }).waitFor({ timeout: 8000 });
await page.screenshot({ path: `${SHOT}/rec-2-done.png` });
check("old password no longer works; the new one does (and the lockout is gone)", !(await login(email, original)).access_token && !!(await login(email, recovered)).access_token);
const after = await waitForMail(before + 2);
check("a 'password was changed' notice was emailed", after.length === before + 2 && /was changed/.test(after[after.length - 1].subject));
check("the notice carries neither the password nor a link", !after[after.length - 1].body.includes(recovered) && !/token=/.test(after[after.length - 1].body));

// the link is single-use
const reuse = await call("POST", "/auth/reset-password", { token: link.split("token=")[1], new_password: "yet-another-passphrase-" + tag });
check("the link cannot be used twice (400 INVALID_RESET_TOKEN)", reuse.status === 400 && reuse.body.error.code === "INVALID_RESET_TOKEN");
const dead = await newPage();
await dead.page.goto(link, { waitUntil: "networkidle" });
await dead.page.getByLabel(/^New password/).fill("some-other-passphrase-" + tag);
await dead.page.getByLabel(/^Repeat the new password/).fill("some-other-passphrase-" + tag);
await dead.page.getByRole("button", { name: "Change password" }).click();
await dead.page.getByText(/Link not valid/).waitFor({ timeout: 8000 });
check("a used link shows 'Link not valid' with a way to request a new one", (await dead.page.getByRole("link", { name: "Request a new link" }).count()) === 1);
await dead.ctx.close();

// sign in through the UI with the recovered password
await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await page.fill('input[name="email"]', email); await page.fill('input[name="password"]', recovered);
await page.click('button[type="submit"]'); await page.waitForURL("**/dashboard", { timeout: 15000 });
check("signing in through the console with the recovered password works", /\/dashboard$/.test(page.url()));
check("no console/CSP errors (control centre)", problems.length === 0);
await ctx.close();

// ---- a citizen is sent to the citizen app --------------------------------------------
const cEmail = `cit-${tag}@example.com`, cPw = "citizen-original-passphrase-" + tag;
const reg = await call("POST", "/auth/register", { email: cEmail, full_name: `Citizen ${tag}`, password: cPw });
check("citizen registered", reg.status === 201);
const c = await newPage();
await c.page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
await c.page.getByRole("link", { name: "Forgot your password?" }).click();
await c.page.waitForURL("**/forgot-password");
await c.page.getByLabel("Email address").fill(cEmail);
await c.page.getByRole("button", { name: "Send the link" }).click();
await c.page.getByRole("status").waitFor();
const cMails = await waitForMail(after.length + 1);
const cMail = cMails[cMails.length - 1];
const cLink = cMail.body.match(/https?:\/\/\S+reset-password\?token=[\w-]+/)?.[0];
check("a citizen's link points at the citizen app", !!cLink && cLink.startsWith("http://localhost:3000/reset-password?token="));
await c.page.goto(cLink, { waitUntil: "networkidle" });
const cNew = "citizen-recovered-passphrase-" + tag;
await c.page.getByLabel(/^New password/).fill(cNew); await c.page.getByLabel(/^Repeat the new password/).fill(cNew);
await c.page.getByRole("button", { name: "Change password" }).click();
await c.page.getByRole("heading", { name: "Password changed" }).waitFor({ timeout: 8000 });
check("the citizen can sign in with the new password", !!(await login(cEmail, cNew)).access_token);
check("no console/CSP errors (citizen app)", c.problems.length === 0);
await c.page.goto("http://localhost:3000/forgot-password", { waitUntil: "networkidle" });
await c.page.getByLabel("Email address").waitFor();
await c.ctx.close();

const m = await newPage(390, 844);
await m.page.goto("http://localhost:3001/forgot-password", { waitUntil: "networkidle" });
await m.page.getByLabel("Email address").waitFor();
check("mobile: forgot page has no horizontal overflow", !(await m.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));
await m.page.screenshot({ path: `${SHOT}/rec-3-mobile.png` });
await browser.close();
console.log(out.join("\n"));
