// Browser check: administrator screens (accounts, hospital registration with an
// operator picker) and the dispatcher's crew picker. Needs a RUNNING stack (API
// :8000 seeded dev data, built control centre :3001), playwright-core (not a
// repository dependency) and Chromium (CHROMIUM_PATH). Not part of check.sh.
// Creates users, a hospital and a resource in the dev DB.
import crypto from "node:crypto";
import { chromium } from "playwright-core";

const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e, p = PW, code) => (await call("POST", "/auth/login", { email: e, password: p, ...(code ? { mfa_code: code } : {}) })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const SHOT = process.env.SHOT_DIR ?? ".";

function b32decode(s) { const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const c of s.replace(/=+$/, "")) bits += A.indexOf(c).toString(2).padStart(5, "0"); const b = []; for (let i = 0; i + 8 <= bits.length; i += 8) b.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(b); }
function totp(secret, off = 0) { const step = Math.floor(Date.now() / 1000 / 30) + off; const m = Buffer.alloc(8); m.writeBigUInt64BE(BigInt(step)); const h = crypto.createHmac("sha1", b32decode(secret)).update(m).digest(); const o = h[19] & 0xf; return String((((h[o] & 0x7f) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3]) % 1_000_000).padStart(6, "0"); }

const admin = await login("admin@raksha.example"), disp = await login("dispatcher@raksha.example");
const tag = Date.now().toString(36).slice(-5);
const mkUser = (suffix, role) => call("POST", "/users", { email: `${suffix}-${tag}@example.com`, full_name: `E2E ${suffix} ${tag}`, password: "e2e-initial-passphrase-" + tag, role }, admin.access_token);
const victimLock = await mkUser("lock", "DISPATCHER");
const victimMfa = await mkUser("mfa", "DISPATCHER");
check("test accounts created via API", victimLock.status === 201 && victimMfa.status === 201);
// lock one account for real: five wrong passwords
for (let i = 0; i < 5; i++) await login(`lock-${tag}@example.com`, "wrong-password-" + i);
check("API reports the account locked", (await login(`lock-${tag}@example.com`, "e2e-initial-passphrase-" + tag)).error?.code === "ACCOUNT_LOCKED");
// give the other account MFA
const mt = (await login(`mfa-${tag}@example.com`, "e2e-initial-passphrase-" + tag)).access_token;
const enr = await call("POST", "/auth/mfa/enroll", {}, mt);
await call("POST", "/auth/mfa/enable", { code: totp(enr.body.secret) }, mt);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
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
async function pollApi(fn, ok, tries = 24) { let r; for (let i = 0; i < tries; i++) { r = await fn(); if (ok(r)) return r; await new Promise((s) => setTimeout(s, 250)); } return r; }

// ---- non-admin cannot reach it ------------------------------------------------
const nd = await signIn("dispatcher@raksha.example");
await nd.page.waitForURL("**/dashboard", { timeout: 15000 });
check("dispatcher sees no Accounts link", (await nd.page.getByRole("link", { name: "Accounts" }).count()) === 0);
await nd.page.goto("http://localhost:3001/admin/users", { waitUntil: "networkidle" });
await nd.page.waitForURL("**/dashboard", { timeout: 8000 });
check("dispatcher typing /admin/users is bounced", /\/dashboard$/.test(nd.page.url()));
check("API refuses the user list to a dispatcher (403)", (await call("GET", "/users", null, disp.access_token)).status === 403);
await nd.ctx.close();

// ---- admin ----------------------------------------------------------------------
const a = await signIn("admin@raksha.example");
await a.page.waitForURL("**/dashboard", { timeout: 15000 });
await a.page.getByRole("link", { name: "Accounts" }).click();
await a.page.getByRole("heading", { name: "ACCOUNTS" }).waitFor();
await a.page.getByLabel("Search accounts").fill(tag);
await a.page.getByRole("list", { name: "Accounts" }).locator("li").first().waitFor();
const rows = await a.page.getByRole("list", { name: "Accounts" }).innerText();
check("search finds both test accounts", rows.includes(`E2E lock ${tag}`) && rows.includes(`E2E mfa ${tag}`));
check("locked account is marked Locked; MFA account shows 2FA on", /Locked/.test(await a.page.getByRole("button", { name: new RegExp(`E2E lock ${tag}`) }).innerText()) && /2FA on/.test(await a.page.getByRole("button", { name: new RegExp(`E2E mfa ${tag}`) }).innerText()));

// unlock
await a.page.getByRole("button", { name: new RegExp(`E2E lock ${tag}`) }).click();
const det = a.page.getByRole("region", { name: "User detail" });
check("detail says locked until …", /Locked until/.test(await det.innerText()));
await det.getByRole("button", { name: "Unlock account" }).click();
const unlocked = await pollApi(() => login(`lock-${tag}@example.com`, "e2e-initial-passphrase-" + tag), (r) => !!r.access_token);
check("after Unlock the user can sign in", !!unlocked.access_token);

// reset MFA
await a.page.getByRole("button", { name: new RegExp(`E2E mfa ${tag}`) }).click();
await det.getByRole("button", { name: "Reset two-factor…" }).click();
check("MFA reset needs confirmation (still on)", (await login(`mfa-${tag}@example.com`, "e2e-initial-passphrase-" + tag)).error?.code === "MFA_REQUIRED");
await det.getByRole("button", { name: "Confirm MFA reset" }).click();
const noMfa = await pollApi(() => login(`mfa-${tag}@example.com`, "e2e-initial-passphrase-" + tag), (r) => !!r.access_token);
check("after reset the user signs in without a code", !!noMfa.access_token);

// role change
await a.page.getByRole("button", { name: new RegExp(`E2E lock ${tag}`) }).click();
await det.getByLabel("Change role").selectOption("RESPONDER");
await det.getByRole("button", { name: "Change role…" }).click();
await det.getByRole("button", { name: "Confirm role change" }).click();
const roleNow = await pollApi(() => call("GET", `/users/${victimLock.body.id}`, null, admin.access_token), (r) => r.body.role === "RESPONDER");
check("role changed to RESPONDER server-side", roleNow.body.role === "RESPONDER");

// deactivate / reactivate
await det.getByRole("button", { name: "Deactivate…" }).click();
await det.getByRole("button", { name: "Confirm deactivate" }).click();
const inactive = await pollApi(() => login(`lock-${tag}@example.com`, "e2e-initial-passphrase-" + tag), (r) => r.error?.code === "ACCOUNT_INACTIVE");
check("deactivated account cannot sign in", inactive.error?.code === "ACCOUNT_INACTIVE");
await det.getByRole("button", { name: "Reactivate" }).click();
const active = await pollApi(() => login(`lock-${tag}@example.com`, "e2e-initial-passphrase-" + tag), (r) => !!r.access_token);
check("reactivated account signs in again", !!active.access_token);

// self-protection
await a.page.getByLabel("Search accounts").fill("admin@raksha.example");
await a.page.getByRole("button", { name: /admin@raksha\.example/ }).first().click();
const selfText = await det.innerText();
check("own row: no deactivate, role change or MFA reset; explanation shown", !/Deactivate…|Reset two-factor/.test(selfText) && (await det.getByLabel("Change role").count()) === 0 && /cannot change your own role/.test(selfText));

// create an operator
await a.page.getByLabel("Search accounts").fill("");
await a.page.getByRole("button", { name: "Create an account" }).click();
const cf = a.page.locator("section", { has: a.page.getByRole("heading", { name: "Create an account" }) });
await cf.getByRole("button", { name: "Create account" }).click();
check("empty create form is blocked with messages", (await cf.getByText(/valid email/i).count()) === 1);
const opEmail = `op-${tag}@example.com`;
await cf.getByLabel(/^Email/).fill(opEmail);
await cf.getByLabel(/^Full name/).fill(`E2E Operator ${tag}`);
await cf.getByLabel("Role", { exact: true }).selectOption("HOSPITAL_OPERATOR");
check("Super administrator is not among the roles offered", (await cf.getByLabel("Role", { exact: true }).locator("option", { hasText: "Super administrator" }).count()) === 0);
await cf.getByRole("button", { name: "Generate" }).click();
await cf.getByRole("button", { name: "Create account" }).click();
const pwShown = (await cf.locator("p[aria-label=\"Initial password\"]").innerText()).trim();
check("password shown once, 20 chars", pwShown.length === 20);
const opLogin = await login(opEmail, pwShown);
if (!opLogin.access_token) out.push("   login response: " + JSON.stringify(opLogin).slice(0, 200) + " pw=" + JSON.stringify(pwShown));
check("the shown password actually works", !!opLogin.access_token && opLogin.user.role === "HOSPITAL_OPERATOR");
if (!opLogin.access_token) { console.log(out.join("\n")); process.exit(1); }
await a.page.screenshot({ path: `${SHOT}/admin-1-created.png` });
await a.page.getByRole("button", { name: "Done" }).click();
const dup = await call("POST", "/users", { email: opEmail, full_name: "Dup Person", password: "another-long-passphrase-1", role: "DISPATCHER" }, admin.access_token);
check("duplicate email is refused by the API (409)", dup.status === 409);
await a.page.screenshot({ path: `${SHOT}/admin-2-accounts.png` });

// hospital registration with the operator picker
await a.page.getByRole("link", { name: "Hospitals" }).click();
await a.page.getByRole("button", { name: "Register a hospital" }).click();
await a.page.getByLabel(/^Code/).fill("ADM-" + tag.toUpperCase());
await a.page.getByLabel(/^Name/).fill("Admin-registered " + tag);
await a.page.getByLabel(/^Latitude/).fill("13.08"); await a.page.getByLabel(/^Longitude/).fill("80.27");
await a.page.getByLabel(/^Total beds/).fill("40"); await a.page.getByLabel(/^Free beds/).fill("9");
const opt = a.page.getByLabel("Hospital operator").locator("option", { hasText: opEmail });
await opt.waitFor({ state: "attached" });
await a.page.getByLabel("Hospital operator").selectOption({ label: `E2E Operator ${tag} (${opEmail})` });
await a.page.getByRole("button", { name: "Register hospital" }).click();
await a.page.getByRole("region", { name: "Hospital detail" }).waitFor({ timeout: 8000 });
const hs = await call("GET", "/hospitals?page_size=100", null, admin.access_token);
const reg = hs.body.items.find((h) => h.code === "ADM-" + tag.toUpperCase());
check("hospital registered and linked to the chosen operator", reg?.managed_by?.id === opLogin.user.id);
const asOp = await call("POST", `/hospitals/${reg.id}/capacity`, { available_beds: 3 }, opLogin.access_token);
check("the linked operator can now maintain its capacity", asOp.status === 200);
check("no console/CSP errors (admin)", a.problems.length === 0);
await a.ctx.close();

// dispatcher: crew picker
const rs = await call("GET", "/users/directory", null, disp.access_token);
check("directory returns responders only, minimal fields", rs.body.every((r) => r.role === "RESPONDER" && Object.keys(r).sort().join() === "full_name,id,role"));
const d = await signIn("dispatcher@raksha.example");
await d.page.waitForURL("**/dashboard", { timeout: 15000 });
await d.page.getByRole("link", { name: "Resources" }).click();
await d.page.getByRole("button", { name: "Register a resource" }).click();
const sign = "CREW-" + tag.toUpperCase();
await d.page.getByLabel(/call sign/i).fill(sign); await d.page.getByLabel(/^name/i).fill("Crew-linked unit");
await d.page.getByLabel(/latitude/i).fill("13.1"); await d.page.getByLabel(/longitude/i).fill("80.3");
await d.page.getByLabel("Crew member").locator("option", { hasText: "Responder" }).first().waitFor({ state: "attached" }).catch(() => {});
const crewOption = rs.body[0];
if (crewOption) await d.page.getByLabel("Crew member").selectOption(crewOption.id);
await d.page.getByRole("button", { name: "Register resource" }).click();
const made = await pollApi(() => call("GET", `/resources?q=${sign}`, null, disp.access_token), (r) => r.body.items?.length === 1);
check("unit linked to the chosen responder", crewOption ? made.body.items[0].operator?.id === crewOption.id : false);
check("no console/CSP errors (dispatcher)", d.problems.length === 0);
await d.ctx.close();

// mobile
const m = await signIn("admin@raksha.example", 390, 844);
await m.page.waitForURL("**/dashboard");
await m.page.goto("http://localhost:3001/admin/users", { waitUntil: "networkidle" });
await m.page.waitForTimeout(1200);
check("mobile: accounts has no horizontal overflow", !(await m.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)));
await m.page.screenshot({ path: `${SHOT}/admin-3-mobile.png`, fullPage: true });
await browser.close();
console.log(out.join("\n"));
