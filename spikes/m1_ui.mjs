// M1 browser check: open the real page, play a bad move by clicking, answer the coach.
// SPENDS MONEY (one Sonnet exchange, about $0.01).
// Installs playwright inside the container's /tmp, so nothing is written to the repo:
//   docker run --rm --network learnchess_default -v "$PWD/spikes:/work" \
//     mcr.microsoft.com/playwright:v1.62.1-noble sh -c 'mkdir -p /tmp/pw && cd /tmp/pw &&
//     npm i --silent playwright@1.62.1 && cp /work/m1_ui.mjs . && node m1_ui.mjs'
import { chromium } from "playwright";

const URL = "http://web:5173/";
const out = (name) => `/work/out/${name}.png`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
page.on("console", (m) => m.type() === "error" && console.log("CONSOLE ERROR:", m.text()));

await page.goto(URL);
// Always start a fresh game as white so the bad move below is legal.
await page.getByRole("button", { name: "New game (white)" }).click();
await page.waitForTimeout(1500);
await page.screenshot({ path: out("ui_1_start") });

const sq = (s) => page.locator(`[data-square="${s}"]`).first();
console.log("model menu:", await page.locator("select").inputValue());
// Timing: a normal move (no coach) at JUDGE_DEPTH=16, click to "Your move." again.
{
  const t0 = Date.now();
  await sq("e2").click();
  await sq("e4").click();
  await page.waitForFunction(() => document.body.innerText.includes("Your move.") &&
    !document.body.innerText.includes("Opponent is thinking"), null, { timeout: 30000 });
  console.log(`TIMING normal move round trip: ${Date.now() - t0} ms`);
  await page.getByRole("button", { name: "New game (white)" }).click();
  await page.waitForTimeout(1500);
}
await sq("g2").click();
await sq("g4").click();
await page.getByText("Why did you play g4?").waitFor({ timeout: 30000 });
console.log("PASS coach asked: Why did you play g4?");
await page.screenshot({ path: out("ui_2_question") });

await page.locator("#reason").fill("I wanted to push my pawn forward");
await page.getByRole("button", { name: "Tell the coach" }).click();
await page.getByRole("button", { name: "Take it back and retry" }).waitFor({ timeout: 60000 });
console.log("PASS coach replied; retry button shown");
await page.screenshot({ path: out("ui_3_reply") });

await page.getByRole("button", { name: "Show me the best move" }).click();
await page.getByText("best move", { exact: true }).waitFor({ timeout: 60000 });
console.log("PASS show-me: best move explained:", (await page.locator("text=best move").locator("..").innerText()).replace(/\s+/g, " ").slice(0, 220));
await page.getByRole("button", { name: "Take it back and retry" }).click();
await page.getByText("Your move.").waitFor({ timeout: 10000 });
await page.waitForTimeout(600); // let the piece animation finish
const advice = await page.getByText("move taken back").count();
console.log(advice ? "PASS advice still visible after retry" : "FAIL advice vanished after retry");
const g4 = await sq("g4").locator("[data-piece]").count();
console.log(g4 === 0 ? "PASS retry: pawn is back off g4" : "FAIL retry: pawn still on g4");
const arrows = await page.locator("svg line, svg path[marker-end], svg polygon").count();
console.log(arrows ? `PASS arrow drawn on board (${arrows} svg elements)` : "FAIL no arrow drawn");
await page.screenshot({ path: out("ui_4_retried") });
await browser.close();
