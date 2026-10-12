// Citizen registration in a real browser, against a real backend, with synthetic data.
//
// Two modes, chosen by EXPECT, because the same page must behave differently depending on how
// the app was BUILT (NEXT_PUBLIC_API_BASE_URL is compiled in):
//
//   EXPECT=connected     the app was built with a real, reachable API address (the local stack:
//                        http://localhost:8000). Registers a new synthetic citizen, lands on
//                        /report, then shows a duplicate attempt being refused by the server.
//   EXPECT=unconfigured  the app was built with the address unset or the `.invalid` placeholder.
//                        Shows the configuration banner, shows submitting names the variable, and
//                        proves no request was sent anywhere.
//
// Needs a RUNNING built citizen app (CITIZEN_URL, default http://localhost:3000), and for
// `connected` a running API, playwright-core (not a repository dependency) and Chromium
// (CHROMIUM_PATH). Not part of check.sh. Creates one synthetic user in whatever database the API
// uses: point it at a development database, never a real one.
import { chromium } from "playwright-core";

const CITIZEN = process.env.CITIZEN_URL ?? "http://localhost:3000";
const EXPECT = process.env.EXPECT ?? "connected";

const out = [];
const check = (label, ok) => out.push(`${ok ? "PASS" : "FAIL"}  ${label}`);

// Synthetic and unique per run: nothing here is a real person's data.
const stamp = Date.now();
const account = {
  name: "Synthetic Tester",
  email: `synthetic.${stamp}@example.org`,
  password: "correct-horse-battery-staple",
};

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium",
  args: ["--no-sandbox"],
});
const page = await (await browser.newContext()).newPage();

const apiRequests = [];
page.on("request", (request) => {
  if (request.url().includes("/api/v1/")) apiRequests.push(`${request.method()} ${request.url()}`);
});
const registerResponses = [];
page.on("response", (response) => {
  if (response.url().endsWith("/api/v1/auth/register")) {
    registerResponses.push(response.status());
  }
});

async function fillAndSubmit() {
  await page.getByLabel(/full name/i).fill(account.name);
  await page.getByLabel(/email address/i).fill(account.email);
  await page.getByLabel(/^password/i).fill(account.password);
  await page.getByRole("button", { name: /create account/i }).click();
}

await page.goto(`${CITIZEN}/register`);

if (EXPECT === "unconfigured") {
  const banner = page.locator('[role="alert"]').first();
  await banner.waitFor({ timeout: 10_000 });
  const bannerText = (await banner.textContent()) ?? "";
  check("a configuration banner is shown before anything is submitted", /not connected/i.test(bannerText));
  check("the banner names the variable to set", bannerText.includes("NEXT_PUBLIC_API_BASE_URL"));

  await fillAndSubmit();
  await page.waitForTimeout(1500);
  const alerts = (await page.locator('[role="alert"]').allTextContents()).join(" | ");
  check("submitting reports the configuration problem", alerts.includes("NEXT_PUBLIC_API_BASE_URL"));
  check("the visitor is not told to 'check your connection'", !/check your connection/i.test(alerts));
  check("no request to any /api/v1 endpoint was sent", apiRequests.length === 0);
  check("the page did not navigate away", page.url().endsWith("/register"));
} else {
  await fillAndSubmit();
  await page.waitForURL(/\/report/, { timeout: 15_000 }).catch(() => {});
  check("registration succeeded and landed on /report", page.url().includes("/report"));
  check("the browser called POST /api/v1/auth/register on the configured API", apiRequests.some((r) => r.startsWith("POST ") && r.includes("/api/v1/auth/register")));
  check("the server answered 201 Created", registerResponses[0] === 201);
  check("no configuration banner is shown", !(await page.getByText(/not connected to its/i).count()));

  // The same email again, from a signed-out browser: the server must refuse it.
  const second = await (await browser.newContext()).newPage();
  second.on("response", (response) => {
    if (response.url().endsWith("/api/v1/auth/register")) registerResponses.push(response.status());
  });
  await second.goto(`${CITIZEN}/register`);
  await second.getByLabel(/full name/i).fill(account.name);
  await second.getByLabel(/email address/i).fill(account.email);
  await second.getByLabel(/^password/i).fill(account.password);
  await second.getByRole("button", { name: /create account/i }).click();
  await second.getByText(/already exists/i).waitFor({ timeout: 10_000 }).catch(() => {});
  check("a duplicate email is refused by the server (409) with its own message", registerResponses.at(-1) === 409 && (await second.getByText(/already exists/i).count()) > 0);
}

await browser.close();
console.log(out.join("\n"));
process.exit(out.some((line) => line.startsWith("FAIL")) ? 1 : 0);
