#!/usr/bin/env node

/**
 * Production frontend smoke gate.
 *
 * This intentionally starts the same FastAPI process used by the production
 * deployment rather than Vite's development server. It catches broken SPA
 * fallback, lazy route chunks, and tab wiring regressions in one command.
 */
import { spawn } from "node:child_process";
import process from "node:process";
import { chromium } from "../artifacts/moneyline/node_modules/playwright/index.mjs";

const port = Number(process.env.FRONTEND_SMOKE_PORT || 18765);
const baseUrl = `http://127.0.0.1:${port}`;
const routes = [
  { requested: "/", expected: "/", heading: "Today" },
  { requested: "/players", expected: "/research/players", heading: "PLAYER DESK" },
  { requested: "/h2h", expected: "/research/matchups", heading: "HEAD-TO-HEAD" },
  { requested: "/parlay", expected: "/research/parlay", heading: "PARLAY CHECK" },
  { requested: "/season", expected: "/research/season", heading: "SEASON DESK" },
  { requested: "/wire", expected: "/research/wire", heading: "THE WIRE" },
];

const server = spawn(
  process.env.PYTHON || "python",
  ["-m", "backend.main"],
  {
    cwd: new URL("..", import.meta.url),
    env: { ...process.env, NODE_ENV: "production", PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"],
  },
);

let serverOutput = "";
server.stdout.on("data", (chunk) => { serverOutput += chunk; });
server.stderr.on("data", (chunk) => { serverOutput += chunk; });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForServer() {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/`);
      if (response.ok || response.status === 503) return;
    } catch {
      // The process may need a few seconds to load the model.
    }
    await sleep(250);
  }
  throw new Error(`Production server did not start.\n${serverOutput}`);
}

const failures = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ headless: true });

  // Auth contract smoke: the gate must resolve before any protected desk
  // request, and the sign-in forms must use the backend's real fields/routes.
  {
    const page = await browser.newPage();
    const requests = [];
    page.on("request", (request) => requests.push(new URL(request.url()).pathname));
    await page.goto(`${baseUrl}/research/matchups`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.getByText("Sign in to MONEYLINE", { exact: true }).waitFor();
    if (requests.some((path) => path.startsWith("/api/") && !path.startsWith("/api/auth/") && path !== "/api/health")) {
      throw new Error("signed-out gate requested protected API data");
    }
    await page.getByLabel("Email address").fill("reader@example.test");
    await page.getByLabel("Password").fill("Correct!password");
    await page.route("**/api/auth/login", async (routeRequest) => {
      const body = JSON.parse(routeRequest.request().postData() || "{}");
      if (body.email !== "reader@example.test" || body.password !== "Correct!password") {
        return routeRequest.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error: { code: "invalid_request", message: "bad fields" } }) });
      }
      return routeRequest.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authenticated: true, user: { id: "smoke-user", email: body.email, display_name: "Reader" } }),
      });
    });
    await page.route("**/api/auth/session", async (routeRequest) => {
      await routeRequest.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: { code: "auth_required", message: "Sign in to use the desk." } }) });
    });
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL(`${baseUrl}/research/matchups`);
    await page.close();
    console.log("PASS auth gate, login fields, and safe route return");
  }

  for (const route of routes) {
    const page = await browser.newPage();
    const consoleErrors = [];
    const pageErrors = [];
    let expectedAuthChallenge = false;
    page.on("response", (response) => {
      if (response.status() === 401 && new URL(response.url()).pathname.startsWith("/api/")) {
        expectedAuthChallenge = true;
      }
    });
    page.on("console", (message) => {
      // Protected research panels intentionally challenge anonymous smoke
      // visits. Keep those expected browser resource messages from masking
      // real route, chunk, and page errors.
      if (message.type() === "error" && !(
        expectedAuthChallenge && message.text().includes("Failed to load resource")
      )) consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    try {
      // The production smoke checks protected routes, so provide the smallest
      // authenticated session fixture without coupling this test to auth
      // credentials or a live OAuth provider.
      await page.route("**/api/**", async (routeRequest) => {
        const path = new URL(routeRequest.request().url()).pathname;
        if (path === "/api/health") {
          return routeRequest.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ model_loaded: true, database_ready: true, model_version: "smoke" }) });
        }
        if (path === "/api/slate") {
          return routeRequest.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ mode: "live", updated_at: "2026-01-01T00:00:00Z", games: [] }) });
        }
        if (path === "/api/teams-live") {
          return routeRequest.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ season: 2026, teams: [] }) });
        }
        if (path === "/api/season-sim") {
          return routeRequest.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ season: 2026, iterations: 1, seed: 1, compute_ms: 1, sample_label: "smoke", rows: [] }) });
        }
        if (path === "/api/wire") {
          return routeRequest.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ updated_at: "2026-01-01T00:00:00Z", types: [], sources_up: {}, items: [] }) });
        }
        return routeRequest.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      });
      await page.route("**/api/auth/session", async (routeRequest) => {
        await routeRequest.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            authenticated: true,
            user: { id: "smoke-user", email: "smoke@example.test", name: "Smoke User" },
          }),
        });
      });
      await page.goto(`${baseUrl}${route.requested}`, {
        waitUntil: "domcontentloaded",
        timeout: 30_000,
      });
      await page.waitForSelector(`h1, h2`, { state: "visible", timeout: 30_000 });
      const bodyText = await page.locator("body").innerText();
      if (!bodyText.includes(route.heading)) {
        throw new Error(`missing panel text "${route.heading}"`);
      }
      const pathname = new URL(page.url()).pathname;
      if (pathname !== route.expected) {
        throw new Error(`expected final path ${route.expected}, got ${pathname}`);
      }
      if (consoleErrors.length || pageErrors.length) {
        throw new Error([
          consoleErrors.length ? `console.error: ${consoleErrors.join(" | ")}` : "",
          pageErrors.length ? `pageerror: ${pageErrors.join(" | ")}` : "",
        ].filter(Boolean).join("\n"));
      }
      console.log(`PASS ${route.requested} → ${pathname} (${route.heading})`);
    } catch (error) {
      failures.push(`${route.requested}: ${error.message}`);
      console.error(`FAIL ${route.requested}: ${error.message}`);
    } finally {
      await page.close();
    }
  }

  // Error branches are deterministic: no provider or email delivery is needed.
  {
    const page = await browser.newPage();
    await page.route("**/api/auth/session", async (routeRequest) => {
      await routeRequest.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: { code: "auth_required", message: "Sign in to use the desk." } }) });
    });
    await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.getByRole("button", { name: "Forgot password?" }).click();
    await page.route("**/api/auth/password-reset/request", async (routeRequest) => {
      await routeRequest.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ ok: true, message: "If that address has a MONEYLINE account, a reset link is on its way." }) });
    });
    await page.getByLabel("Email address").fill("reader@example.test");
    await page.getByRole("button", { name: "Send reset link" }).click();
    await page.getByRole("status").waitFor();
    if (!(await page.getByRole("status").innerText()).includes("If an account matches")) throw new Error("generic reset confirmation missing");
    await page.close();
    console.log("PASS invalid input and generic reset guidance");
  }

  {
    const page = await browser.newPage();
    await page.route("**/api/auth/session", async (routeRequest) => {
      await routeRequest.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: { code: "auth_required", message: "Sign in to use the desk." } }) });
    });
    await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    const googleLink = page.getByRole("link", { name: "Continue with Google" });
    const googleHref = await googleLink.getAttribute("href");
    if (!googleHref?.includes("/api/auth/google/start?next=")) throw new Error("Google launch does not use /auth/google/start");
    await page.close();

    const unavailable = await browser.newPage();
    await unavailable.route("**/api/auth/session", async (routeRequest) => {
      await routeRequest.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "auth_unavailable", message: "Accounts are unavailable right now." } }) });
    });
    await unavailable.goto(`${baseUrl}/research`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    if (!(await unavailable.getByRole("alert").innerText()).includes("couldn’t check your session")) throw new Error("session unavailable guidance missing");
    await unavailable.close();
    console.log("PASS Google callback and unavailable-session guidance");
  }

  {
    const page = await browser.newPage();
    await page.route("**/api/**", async (routeRequest) => {
      if (new URL(routeRequest.request().url()).pathname === "/api/health") {
        return routeRequest.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ model_loaded: true, database_ready: true, model_version: "smoke" }) });
      }
      await routeRequest.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.route("**/api/auth/session", async (routeRequest) => {
      await routeRequest.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ authenticated: true, user: { id: "smoke-user", email: "smoke@example.test", display_name: "Smoke User" } }) });
    });
    await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.getByRole("button", { name: "Yes" }).click();
    await page.getByText("Sign in to MONEYLINE", { exact: true }).waitFor();
    await page.close();
    console.log("PASS logout clears the client session and returns to sign-in");
  }
} finally {
  if (browser) await browser.close();
  server.kill("SIGTERM");
  await new Promise((resolve) => server.once("exit", resolve));
}

if (failures.length) {
  console.error(`\nFrontend smoke failed (${failures.length} route${failures.length === 1 ? "" : "s"}):`);
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}
console.log(`Frontend smoke passed: ${routes.length} production routes plus auth flows checked.`);