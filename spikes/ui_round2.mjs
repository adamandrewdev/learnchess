// Browser check for feedback round 2: skip buttons, arrow lifetime, game-over banner.
// SPENDS MONEY (one Sonnet reply + one reveal, about $0.02). MATE_GAME = id of a game one
// move from Qh5# for white (inserted for the test).
import process from "node:process";
import { chromium } from "playwright";

const URL = "http://web:5173/";
const MATE_GAME = process.env.MATE_GAME;
const out = (n) => `/work/out/${n}.png`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
const sq = (s) => page.locator(`[data-square="${s}"]`).first();
const arrowCount = () => page.locator("svg line, svg polygon").count();
const spendText = () => page.getByText(/^\$\d+\.\d\d \/ \$/).innerText();
const pass = (ok, msg) => console.log(`${ok ? "PASS" : "FAIL"} ${msg}`);

await page.goto(URL);
if (!process.env.ONLY_MATE) {
await page.getByRole("button", { name: "New game (white)" }).click();
await page.waitForTimeout(1500);

// 1. Skip straight from the question, no typing, no spend.
const spendBefore = await spendText();
await sq("g2").click();
await sq("g4").click();
await page.getByText("Why did you play g4?").waitFor({ timeout: 30000 });
await page.getByRole("button", { name: "Skip: take it back" }).click();
await page.getByText("Your move.").waitFor({ timeout: 10000 });
await page.waitForTimeout(600);
pass((await sq("g4").locator("[data-piece]").count()) === 0, "skip + take back: pawn back on g2");
pass((await page.getByText("Skipped").count()) > 0, "skipped exchange shown in the panel");
pass((await spendText()) === spendBefore, `no spend for skipping (${spendBefore})`);
await page.screenshot({ path: out("r2_1_skipped") });

// 2. Arrow appears after show-me + take back, and disappears once a move is made.
await sq("g2").click();
await sq("g4").click();
await page.getByText("Why did you play g4?").last().waitFor({ timeout: 30000 });
await page.locator("#reason").fill("pushing a pawn");
await page.getByRole("button", { name: "Tell the coach" }).click();
await page.getByRole("button", { name: "Show me the best move" }).waitFor({ timeout: 60000 });
await page.getByRole("button", { name: "Show me the best move" }).click();
await page.getByText("best move", { exact: true }).waitFor({ timeout: 60000 });
await page.getByRole("button", { name: "Take it back and retry" }).click();
await page.getByText("Your move.").waitFor({ timeout: 10000 });
await page.waitForTimeout(600);
pass((await arrowCount()) > 0, "arrow shown on the taken-back position");
await sq("d2").click();
await sq("d4").click();
await page.waitForTimeout(400);
pass((await arrowCount()) === 0, "arrow gone immediately after moving");
await page.screenshot({ path: out("r2_2_arrow_gone") });

}
// 3. Checkmate shows the banner and a way into a new game.
await page.evaluate((id) => localStorage.setItem("learnchess.gameId", id), MATE_GAME);
await page.reload();
await page.waitForTimeout(1500);
await sq("d1").click();
await sq("h5").click();
await page.getByText("Checkmate. You won!").first().waitFor({ timeout: 30000 });
await page.waitForTimeout(500); // let the queen's move animation finish
pass(true, "checkmate banner: Checkmate. You won!");
await page.screenshot({ path: out("r2_3_checkmate") });
await page.getByRole("button", { name: "New game as white" }).click();
await page.getByText("No moves yet.").waitFor({ timeout: 10000 });
pass((await page.getByText("Checkmate. You won!").count()) === 0, "new game from the banner");
await browser.close();
