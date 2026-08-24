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

  for (const route of routes) {
    const page = await browser.newPage();
    const consoleErrors = [];
    const pageErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    try {
      // The production smoke checks protected routes, so provide the smallest
      // authenticated session fixture without coupling this test to auth
      // credentials or a live OAuth provider.
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
console.log(`Frontend smoke passed: ${routes.length} production routes checked.`);