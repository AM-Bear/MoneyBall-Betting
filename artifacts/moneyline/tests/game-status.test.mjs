import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let vite;
let gameStatus;

before(async () => {
  vite = await createServer({
    root: new URL("..", import.meta.url).pathname,
    configFile: false,
    logLevel: "error",
    server: { middlewareMode: true },
    optimizeDeps: { noDiscovery: true },
  });
  gameStatus = await vite.ssrLoadModule("/src/lib/game-status.ts");
});

after(async () => {
  await vite?.close();
});

const scheduledGame = {
  away: "NYY",
  home: "BOS",
  status: "Scheduled",
  model_prob_home: 0.54,
  fair_lines: { away: 115, home: -115 },
};

test("scheduled games allow the pregame manual price check", () => {
  assert.equal(gameStatus.manualPriceCheckState(scheduledGame), "available");
});

test("in-progress games never expose a manual price verdict", () => {
  assert.equal(
    gameStatus.manualPriceCheckState({ ...scheduledGame, status: "In Progress" }),
    "in-progress",
  );
});

test("final games never expose a manual price verdict", () => {
  assert.equal(
    gameStatus.manualPriceCheckState({ ...scheduledGame, status: "Final" }),
    "final",
  );
});

test("postponed and suspended games never expose a manual price verdict", () => {
  for (const status of ["Postponed", "Suspended"]) {
    const game = { ...scheduledGame, status };
    assert.equal(gameStatus.manualPriceCheckState(game), "unavailable");
    assert.equal(gameStatus.isNonPlayableGame(game), true);
  }
});
test("the evaluate status enum is derived from the same predicates", () => {
  const cases = [
    ["Scheduled", "scheduled"],
    ["Pre-Game", "scheduled"],
    ["In Progress", "live"],
    ["Delayed", "live"],
    ["Final", "final"],
    ["Game Over", "final"],
    ["Postponed", "postponed"],
    ["Suspended", "postponed"],
  ];
  for (const [status, expected] of cases) {
    assert.equal(gameStatus.evaluationStatus({ ...scheduledGame, status }), expected, status);
  }
});
