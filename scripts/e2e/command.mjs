// Browser check against a RUNNING stack (API :8000 seeded dev data; apps :3000/:3001/:3002 built).
// Needs playwright-core (not a repository dependency) and Chromium (CHROMIUM_PATH). Not part of check.sh.
// Creates incidents/resources in the dev DB. Prints PASS/FAIL per check.
import { chromium } from "playwright-core";
const API = "http://localhost:8000/api/v1", PW = "raksha-development-only";
const j = async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) });
const call = (m, p, b, t) => fetch(API + p, { method: m, headers: { "content-type": "application/json", ...(t ? { authorization: `Bearer ${t}` } : {}) }, body: b ? JSON.stringify(b) : undefined }).then(j);
const login = async (e) => (await call("POST", "/auth/login", { email: e, password: PW })).body;
const out = []; const check = (l, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${l}`);

const disp = await login("dispatcher@raksha.example"), cit = await login("citizen@raksha.example");
// A fresh critical incident near the map centre (Chennai) so the viewport feed has data.
const inc = await call("POST", "/incidents", { category: "BUILDING_COLLAPSE", description: "Building collapsed, people trapped under rubble (command e2e)", latitude: 13.0827, longitude: 80.2707, people_affected: 4, people_trapped: true, immediate_danger: true, medical_required: true }, cit.access_token);
check("incident created", inc.status === 201);
await call("POST", "/resources", { call_sign: "CMD-" + Date.now().toString(36).slice(-4).toUpperCase(), name: "Command E2E Rescue", resource_type: "RESCUE_TEAM", latitude: 13.09, longitude: 80.28, crew_size: 6, capabilities: ["heavy_rescue"] }, disp.access_token);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
async function session(w, h, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, ...opts });
  const page = await ctx.newPage(); const problems = [];
  page.on("console", (m) => { if (/content security policy|refused to|error/i.test(m.text()) && !/tile\.openstreetmap|ERR_(NAME|INTERNET|CONNECTION|TUNNEL|PROXY)|Failed to load resource/i.test(m.text())) problems.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 200)));
  return { ctx, page, problems };
}
const { ctx, page, problems } = await session(1440, 1000);
await page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await page.fill('input[name="email"]', "dispatcher@raksha.example"); await page.fill('input[name="password"]', PW);
await page.click('button[type="submit"]'); await page.waitForURL("**/dashboard", { timeout: 15000 });
await page.waitForSelector(".leaflet-marker-icon", { timeout: 15000 });
await page.waitForTimeout(1500);
check("command strip: connected + data freshness", (await page.getByRole("status").innerText()).includes("Connected") && /Data updated/.test(await page.getByRole("status").innerText()));
check("sidebar nav present with active item", (await page.locator('nav[aria-label="Modules"] a[aria-current="page"]').innerText()) === "Command centre");
const markers = await page.locator(".leaflet-marker-icon").count();
check(`map shows markers (${markers})`, markers > 0);
await page.locator("details[aria-label='Map legend'] summary").click();
check("legend lists priorities with words", /Critical/.test(await page.locator("details[aria-label='Map legend']").innerText()));
const labelled = await page.locator('.leaflet-marker-icon[title*="priority"], .leaflet-marker-icon[title*="incidents, most urgent"]').count();
check(`markers carry text labels, not colour alone (${labelled})`, labelled > 0);
await page.getByRole("button", { name: new RegExp(inc.body.reference_code) }).click();
await page.getByRole("region", { name: "Selected incident" }).waitFor();
await page.waitForTimeout(1200);
const sel = (await page.getByRole("region", { name: "Selected incident" }).innerText()).replace(/\s+/g, " ");
check("selected panel: AI proposal labelled not-verified", /AI proposal — not verified/.test(sel));
check("selected panel: engine score + factors", /engine score \d+/i.test(sel));
check("selected panel: suggestions-only wording, ETA labelled estimate", /Suggestions only/.test(sel));
check("selected panel offers no dispatch button (console only)", (await page.getByRole("region", { name: "Selected incident" }).getByRole("button", { name: /dispatch/i }).count()) === 0);
const tl = (await page.getByRole("region", { name: "Incident activity" }).innerText()).replace(/\s+/g, " ");
check("timeline shows real history", /Reported/.test(tl));
await page.screenshot({ path: `${process.env.SHOT_DIR ?? "."}/cmd-1-dashboard.png`, fullPage: false });

// resources layer toggle
const resBefore = await page.locator('.leaflet-marker-icon[title*="Rescue"], .leaflet-marker-icon[title*="CMD-"]').count();
check(`resource markers visible (${resBefore})`, resBefore > 0);
await page.getByLabel(/^Resources/).uncheck(); await page.waitForTimeout(500);
check("resource layer toggles off", (await page.locator('.leaflet-marker-icon[title*="CMD-"]').count()) === 0);
await page.getByLabel(/^Resources/).check();

// filters
await page.getByLabel("Filter by priority").selectOption("LOW"); await page.waitForTimeout(1200);
check("priority filter narrows the queue (no LOW incidents -> empty state)", /No incidents match/.test(await page.locator("body").innerText()));
await page.getByLabel("Filter by priority").selectOption("");

// globe overview
await page.getByRole("button", { name: "Globe overview" }).click(); await page.waitForTimeout(2500);
check("globe overview renders a canvas", (await page.locator("section[aria-label='Globe overview'] canvas").count()) === 1);
await page.screenshot({ path: `${process.env.SHOT_DIR ?? "."}/cmd-2-globe.png` });
await page.getByRole("button", { name: "Operational map" }).click(); await page.waitForTimeout(1000);
check("back to the operational map", (await page.locator(".leaflet-container").count()) === 1);

// notifications bell
const bell = page.getByRole("button", { name: /^Notifications/ });
check("notification bell present", await bell.count() === 1);
const label = await bell.getAttribute("aria-label");
await bell.click(); await page.waitForTimeout(800);
const panel = (await page.getByRole("region", { name: "Notifications" }).innerText()).replace(/\s+/g, " ");
check(`inbox opens (${label})`, /Notifications/.test(panel));
await page.screenshot({ path: `${process.env.SHOT_DIR ?? "."}/cmd-3-inbox.png` });
await page.keyboard.press("Escape");

// keyboard-reachable markers
check("markers are keyboard focusable", (await page.locator(".leaflet-marker-icon").first().getAttribute("tabindex")) === "0");

check("no CSP violations or console errors (desktop)", problems.length === 0);
if (problems.length) out.push("   " + problems.join(" | "));
await ctx.close();

// mobile
const m = await session(390, 844, { isMobile: true, hasTouch: true });
await m.page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await m.page.fill('input[name="email"]', "dispatcher@raksha.example"); await m.page.fill('input[name="password"]', PW);
await m.page.click('button[type="submit"]'); await m.page.waitForURL("**/dashboard"); await m.page.waitForTimeout(2500);
const overflow = await m.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
check("mobile: no horizontal overflow", !overflow);
await m.page.screenshot({ path: `${process.env.SHOT_DIR ?? "."}/cmd-4-mobile.png`, fullPage: true });
check("mobile: no console errors", m.problems.length === 0);
if (m.problems.length) out.push("   " + m.problems.join(" | "));

// reduced motion
const r = await session(1440, 900, { reducedMotion: "reduce" });
await r.page.goto("http://localhost:3001/login", { waitUntil: "networkidle" });
await r.page.fill('input[name="email"]', "dispatcher@raksha.example"); await r.page.fill('input[name="password"]', PW);
await r.page.click('button[type="submit"]'); await r.page.waitForURL("**/dashboard"); await r.page.waitForTimeout(2000);
const anim = await r.page.evaluate(() => document.getAnimations().filter((a) => a.effect && a.playState === "running" && /raksha-ring|grid-drift/.test(a.animationName ?? "")).length);
check("reduced motion: no running ring/grid animations", anim === 0);
await browser.close();
console.log(out.join("\n"));
