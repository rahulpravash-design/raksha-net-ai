// Check the per-request Content-Security-Policy on all three front ends: a fresh nonce per
// request, no 'unsafe-inline' for scripts, every rendered script carrying the nonce, the
// apps still working, and injected markup that tries to run code NOT running.
// Needs a RUNNING stack (built apps on :3000/:3001/:3002, API :8000), playwright-core
// (not a repository dependency) and Chromium (CHROMIUM_PATH). Not part of check.sh.
import { chromium } from "playwright-core";

const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);
const APPS = { citizen: "http://localhost:3000", control: "http://localhost:3001", responder: "http://localhost:3002" };
const PAGES = { citizen: ["/", "/login", "/register"], control: ["/", "/login", "/forgot-password"], responder: ["/", "/login"] };

const scriptSrc = (policy) => (policy.split(";").map((d) => d.trim()).find((d) => d.startsWith("script-src")) ?? "");
const nonceOf = (policy) => scriptSrc(policy).match(/'nonce-([^']+)'/)?.[1];

// ---- headers and markup ----------------------------------------------------------------------
for (const [app, base] of Object.entries(APPS)) {
  for (const path of PAGES[app]) {
    const first = await fetch(base + path), second = await fetch(base + path);
    const policy = first.headers.get("content-security-policy") ?? "";
    const html = await first.text();
    const nonce = nonceOf(policy);
    check(`${app}${path}: a nonce is issued`, !!nonce);
    check(`${app}${path}: script-src has no 'unsafe-inline'`, !scriptSrc(policy).includes("unsafe-inline"));
    check(`${app}${path}: production build has no 'unsafe-eval'`, !scriptSrc(policy).includes("unsafe-eval"));
    check(`${app}${path}: a different nonce on the next request`, nonceOf(second.headers.get("content-security-policy") ?? "") !== nonce);
    const scripts = [...html.matchAll(/<script\b[^>]*>/g)].map((m) => m[0]);
    const unsigned = scripts.filter((tag) => !tag.includes(`nonce="${nonce}"`));
    check(`${app}${path}: all ${scripts.length} rendered scripts carry this request's nonce`, scripts.length > 0 && unsigned.length === 0);
  }
}

// ---- in a browser ------------------------------------------------------------------------------
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
for (const [app, base] of Object.entries(APPS)) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const violations = [], refusedInjected = [];
  page.on("console", (m) => {
    const text = m.text();
    if (/inline event handler|__pwned/i.test(text)) refusedInjected.push(text.slice(0, 160));
    else if (/content security policy|refused to/i.test(text)) violations.push(text.slice(0, 200));
  });
  page.on("pageerror", (e) => violations.push("pageerror: " + e.message.slice(0, 160)));
  // An attacker who got markup into the server-rendered page (stored or reflected
  // injection): the response is served with its real policy, plus an injected script.
  await page.route(base + "/login", async (route) => {
    const response = await route.fetch();
    const body = (await response.text()).replace("</body>", "<script>window.__pwned2 = 1</script></body>");
    await route.fulfill({ response, body });
  });
  await page.goto(base + "/login", { waitUntil: "networkidle" });
  const hydrated = await page.evaluate(() => document.querySelectorAll("input").length > 0);
  // Interactivity proves the nonce'd scripts ran: a failed sign-in is answered by React.
  await page.fill('input[name="email"]', "nobody@example.com");
  await page.fill('input[name="password"]', "wrong-password-123");
  await page.click('button[type="submit"]');
  const answered = await page.getByRole("alert").first().waitFor({ timeout: 8000 }).then(() => true, () => false);
  check(`${app}: the page hydrates and its scripts run under the policy`, hydrated && answered);

  // Injected markup with an inline handler, added after load (e.g. via an HTML sink).
  await page.evaluate(() => {
    document.body.insertAdjacentHTML("beforeend", '<img src="data:x" onerror="window.__pwned = 1">');
  });
  await page.waitForTimeout(500);
  const pwned = await page.evaluate(() => [window.__pwned ?? null, window.__pwned2 ?? null]);
  check(`${app}: an injected onerror= handler does not run`, pwned[0] === null);
  check(`${app}: a <script> injected into the server-rendered page does not run`, pwned[1] === null);
  check(`${app}: the browser reported refusing it`, refusedInjected.length + violations.filter((v) => /inline script/i.test(v)).length > 0);
  check(`${app}: no other CSP violations or page errors`, violations.filter((v) => !/inline script/i.test(v)).length === 0);
  await ctx.close();
}

// The heaviest page: the 3D landing (three.js, motion) must still render under the policy.
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage(); const problems = [];
  page.on("console", (m) => { if (/content security policy|refused to/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
  await page.goto(APPS.control + "/", { waitUntil: "networkidle" }); await page.waitForTimeout(2500);
  check("control /: the 3D globe renders (canvas) with no CSP violations", (await page.locator("canvas").count()) > 0 && problems.length === 0);
  await ctx.close();
}
await browser.close();
console.log(out.join("\n"));
process.exit(out.some((l) => l.startsWith("FAIL")) ? 1 : 0);
