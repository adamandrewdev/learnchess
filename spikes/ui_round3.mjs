// Browser check for feedback round 3: good-move takeback confirmation, quick replies, layout.
// Needs the api started with GOOD_MOVE_CHECK_RATE=1. SPENDS MONEY (one Sonnet reply, ~$0.01).
import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
const sq = (s) => page.locator(`[data-square="${s}"]`).first();
const pass = (ok, msg) => console.log(`${ok ? "PASS" : "FAIL"} ${msg}`);

await page.goto("http://web:5173/");
pass((await page.locator("header", { hasText: "Coach model" }).count()) === 0, "top bar gone");
await page.getByRole("button", { name: "New game (white)" }).click();
await page.waitForTimeout(1500);

// 1. Good move -> neutral question -> skip+take back -> confirmation -> keep it.
await sq("e2").click();
await sq("e4").click();
await page.getByText("Why did you play e4?").waitFor({ timeout: 30000 });
// Only the conversation area: a quick-reply button itself says "...a good move".
const convo = page.locator("section", { hasText: "Coach" }).locator("div.overflow-y-auto");
pass(!/good move|blunder|mistake|inaccuracy/i.test(await convo.innerText()), "question doesn't hint");
await page.getByRole("button", { name: "Skip: take it back" }).click();
await page.getByText("That was a good move.").waitFor({ timeout: 10000 });
pass(true, "confirmation shown before taking back a good move");
await page.screenshot({ path: "/work/out/r3_1_confirm.png" });
await page.getByRole("button", { name: "Keep my move" }).click();
await page.getByText("Your move.").waitFor({ timeout: 30000 });
await page.waitForTimeout(500);
pass((await sq("e4").locator("[data-piece]").count()) === 1, "kept: pawn still on e4");

// 2. Quick reply sends with one click.
await sq("d2").click();
await sq("d4").click();
await page.getByText("Why did you play d4?").waitFor({ timeout: 30000 });
await page.getByRole("button", { name: "Getting a piece out" }).click();
await page.getByRole("button", { name: "Keep my move" }).waitFor({ timeout: 60000 });
pass((await page.getByText("Getting a piece out").count()) > 0, "quick reply sent and shown");
await page.screenshot({ path: "/work/out/r3_2_layout.png" });
await browser.close();
