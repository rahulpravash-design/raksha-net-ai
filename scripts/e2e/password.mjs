// Browser check: changing your password, the forced change for administrator-set
// passwords, and the administrator's temporary-password reset. Needs a RUNNING
// stack (API :8000 seeded dev data, built control centre :3001), playwright-core
// (not a repository dependency) and Chromium (CHROMIUM_PATH). Not part of
// check.sh. Creates users in the dev DB.
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e, p) => (await call("POST", "/auth/login", { email: e, password: p })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";

const admin = await login("admin@raksha.example", PW);
const tag = Date.now().toString(36).slice(-5);
const email = `pw-${tag}@example.com`, temp = "admin-chosen-passphrase-" + tag, mine = "my-very-own-passphrase-" + tag, later = "a-third-passphrase-" + tag;
const made = await call("POST", "/users", { email, full_name: `PW Tester ${tag}`, password: temp, role: "DISPATCHER" }, admin.access_token);
check("admin-created account is flagged must_change_password", made.status === 201 && made.body.must_change_password === true);
const first = await login(email, temp);
const blocked = await call("GET", "/incidents", null, first.access_token);
check("API refuses everything else until it is changed (PASSWORD_CHANGE_REQUIRED)", blocked.status === 403 && blocked.body.error?.code === "PASSWORD_CHANGE_REQUIRED");

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
const page = await ctx.newPage(); const problems = [];
page.on("console", (m) => { if (/content security policy|refused to/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
async function uiLogin(pw) {
  await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', email); await page.fill('input[name="password"]', pw);
  await page.click('button[type="submit"]');
}

// ---- forced change ---------------------------------------------------------------
await uiLogin(temp);
await page.waitForURL("**/account/security", { timeout: 15000 });
check("signing in with an administrator-set password lands on the security screen", /\/account\/security$/.test(page.url()));
const pwPanel = page.getByRole("region", { name: "Password" });
check("explains that the password is known to an administrator", /administrator set your password/i.test(await pwPanel.getByRole("note").innerText()));
await page.goto("http://localhost:3001/dashboard", { waitUntil: "networkidle" });
await page.waitForURL("**/account/security", { timeout: 10000 });
check("going to /dashboard bounces back to the security screen", /\/account\/security$/.test(page.url()));
await page.screenshot({ path: `${SHOT}/pw-1-forced.png` });

// client-side checks
await pwPanel.getByLabel(/^Current password/).fill(temp);
await pwPanel.getByLabel(/^New password/).fill(mine);
await pwPanel.getByLabel(/^Repeat the new password/).fill(mine + "x");
await pwPanel.getByRole("button", { name: "Change password" }).click();
check("mismatched confirmation is caught before any request", (await pwPanel.getByText(/do not match/i).count()) === 1);
// server-side refusals
await pwPanel.getByLabel(/^Repeat the new password/).fill("short");
await pwPanel.getByLabel(/^New password/).fill("short");
await pwPanel.getByRole("button", { name: "Change password" }).click();
await pwPanel.getByRole("alert").waitFor({ timeout: 8000 });
check("a weak password is refused with the server's message", /at least|too common|characters/i.test(await pwPanel.getByRole("alert").innerText()));
await pwPanel.getByLabel(/^Current password/).fill("not-the-current-password");
await pwPanel.getByLabel(/^New password/).fill(mine); await pwPanel.getByLabel(/^Repeat the new password/).fill(mine);
await pwPanel.getByRole("button", { name: "Change password" }).click();
await page.waitForFunction(() => /incorrect/i.test(document.querySelector('[role="alert"]')?.textContent ?? ""), null, { timeout: 8000 });
check("a wrong current password is refused (and the session is not logged out)", /\/account\/security$/.test(page.url()));
// success
await pwPanel.getByLabel(/^Current password/).fill(temp);
await pwPanel.getByLabel(/^New password/).fill(mine); await pwPanel.getByLabel(/^Repeat the new password/).fill(mine);
await pwPanel.getByRole("button", { name: "Change password" }).click();
await page.waitForURL("**/dashboard", { timeout: 15000 });
check("after the forced change the user is sent to their home screen", /\/dashboard$/.test(page.url()));
await page.waitForTimeout(1200);
check("the console now works (queue loads, no redirect back)", /\/dashboard$/.test(page.url()) && (await page.locator("body").innerText()).includes("COMMAND CENTRE"));
const flagged = await call("GET", `/users/${made.body.id}`, null, admin.access_token);
check("server cleared must_change_password", flagged.body.must_change_password === false);
check("old password no longer works; new one does", !(await login(email, temp)).access_token && !!(await login(email, mine)).access_token);

// ---- voluntary change, with the other session ended ---------------------------------
const otherSession = await login(email, mine);
await page.getByRole("link", { name: "Security" }).click();
await page.waitForURL("**/account/security");
check("no forced-change banner for a voluntary change", (await pwPanel.getByRole("note").count()) === 0);
await pwPanel.getByLabel(/^Current password/).fill(mine);
await pwPanel.getByLabel(/^New password/).fill(later); await pwPanel.getByLabel(/^Repeat the new password/).fill(later);
await pwPanel.getByRole("button", { name: "Change password" }).click();
await pwPanel.getByRole("status").waitFor({ timeout: 8000 });
check("says other sessions were signed out", /other sessions have been signed out/i.test(await pwPanel.getByRole("status").innerText()));
const stale = await call("POST", "/auth/refresh", { refresh_token: otherSession.refresh_token });
check("the other device's refresh token no longer works", stale.status === 401);
await page.reload({ waitUntil: "networkidle" });
check("this browser's session continued (still signed in after reload)", /\/account\/security$/.test(page.url()));
check("no console/CSP errors (user)", problems.length === 0);
await ctx.close();

// ---- admin temporary password -----------------------------------------------------------
const actx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
const apage = await actx.newPage();
await apage.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await apage.fill('input[name="email"]', "admin@raksha.example"); await apage.fill('input[name="password"]', PW);
await apage.click('button[type="submit"]'); await apage.waitForURL("**/dashboard", { timeout: 15000 });
await apage.goto("http://localhost:3001/admin/users", { waitUntil: "networkidle" });
await apage.getByLabel("Search accounts").fill(`pw-${tag}`);
await apage.getByRole("button", { name: new RegExp(`PW Tester ${tag}`) }).click();
const det = apage.getByRole("region", { name: "User detail" });
check("detail shows the password as chosen by the user", /Chosen by the user/.test(await det.innerText()));
// lock the account for real, then reset
for (let i = 0; i < 5; i++) await login(email, "wrong-password-" + i);
check("account is locked", (await login(email, later)).error?.code === "ACCOUNT_LOCKED");
await apage.getByRole("button", { name: new RegExp(`PW Tester ${tag}`) }).click();
await det.getByRole("button", { name: "Set temporary password…" }).click();
check("nothing changes before the confirmation", (await login(email, later)).error?.code === "ACCOUNT_LOCKED");
await det.getByRole("button", { name: "Generate" }).click();
const tempShown = await det.getByLabel(/^Temporary password/).inputValue();
check("a 20-character password was generated", tempShown.length === 20);
await det.getByRole("button", { name: "Confirm temporary password" }).click();
const shownEl = det.locator('p[aria-label="Temporary password"]');
await shownEl.waitFor({ timeout: 8000 });
check("the temporary password is shown once", (await shownEl.innerText()).trim() === tempShown);
await apage.screenshot({ path: `${SHOT}/pw-2-admin-reset.png` });
const afterReset = await login(email, tempShown);
check("reset cleared the lockout and the temporary password works", !!afterReset.access_token && afterReset.user.must_change_password === true);
check("old password no longer works", !(await login(email, later)).access_token);
check("the detail now says an administrator set it", /must be changed at next sign-in/.test(await det.innerText()));
await apage.getByLabel("Search accounts").fill("admin@raksha.example");
await apage.getByRole("button", { name: /admin@raksha\.example/ }).first().click();
check("an administrator is not offered a temporary password for themselves", (await det.getByRole("button", { name: /Set temporary password/ }).count()) === 0);
await actx.close();

const m = await browser.newContext({ viewport: { width: 390, height: 844 } });
const mp = await m.newPage();
await mp.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await mp.fill('input[name="email"]', "dispatcher@raksha.example"); await mp.fill('input[name="password"]', PW);
await mp.click('button[type="submit"]'); await mp.waitForURL("**/dashboard", { timeout: 15000 });
await mp.goto("http://localhost:3001/account/security", { waitUntil: "networkidle" });
await mp.waitForTimeout(800);
check("mobile: security screen has no horizontal overflow", !(await mp.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));
await mp.screenshot({ path: `${SHOT}/pw-3-mobile.png`, fullPage: true });
await browser.close();
console.log(out.join("\n"));
