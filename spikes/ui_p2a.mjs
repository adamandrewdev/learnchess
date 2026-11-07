// M2 browser check (PLAN P2a): quiet play, blunder warning, think time. No API spend.
// Run against the throwaway lctest stack (spikes/compose.test.yml), so test games stay out of
// your real history:
//   docker run --rm --network lctest_default -v "$PWD/spikes:/work" \
//     mcr.microsoft.com/playwright:v1.62.1-noble sh -c 'mkdir -p /tmp/pw && cd /tmp/pw &&
//     npm i --silent playwright@1.62.1 && cp /work/ui_p2a.mjs . && node ui_p2a.mjs'
// Then check think_ms in the lctest database (see the PLAN M2 conditions).
import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
page.on("console", (m) => m.type() === "error" && console.log("CONSOLE ERROR:", m.text()));
const sq = (s) => page.locator(`[data-square="${s}"]`).first();
const pass = (ok, msg) => console.log(`${ok ? "PASS" : "FAIL"} ${msg}`);
const yourMove = () => page.getByText("Your move.").waitFor({ timeout: 60000 });
const warning = page.locator('[role="alert"]', { hasText: "⚠" });

async function move(from, to) {
  await sq(from).click();
  await sq(to).click();
}

async function setHidden(hidden) {
  await page.evaluate((h) => {
    Object.defineProperty(document, "hidden", { get: () => h, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  }, hidden);
}

await page.goto("http://web:5173/");
await page.getByRole("button", { name: "New game (white)" }).click();
await yourMove();

// 1. A slightly weak move in a level position: no warning, bot just replies. ~2 s think.
await page.waitForTimeout(2000);
await move("a2", "a3");
await page.waitForTimeout(300);
await yourMove();
pass((await warning.count()) === 0, "a3 (quiet inaccuracy at most) did not warn");

// 2. Think time excludes a hidden tab: ~1 s visible, 3 s hidden, ~1 s visible.
await page.waitForTimeout(1000);
await setHidden(true);
await page.waitForTimeout(3000);
await setHidden(false);
await page.waitForTimeout(1000);
await move("e2", "e4");
await page.waitForTimeout(300);
await yourMove();
pass((await warning.count()) === 0, "e4 did not warn");

// 3. Hang the bishop on a6 (attacked by the b7 pawn / b8 knight): warning, then take back.
// The bot is random, so it may block the diagonal; if so, start fresh games until it's open.
const has = async (s) => (await sq(s).locator("[data-piece]").count()) > 0;
async function a6IsAHang() {
  for (const s of ["e2", "d3", "c4", "b5", "a6"]) if (await has(s)) return false;
  return (await has("b7")) || (await has("b8"));
}
for (let attempt = 0; !(await a6IsAHang()); attempt++) {
  if (attempt === 5) throw new Error("couldn't get an open f1-a6 diagonal in 5 games");
  await page.getByRole("button", { name: "New game (white)" }).click();
  await yourMove();
  await move("e2", "e4");
  await page.waitForTimeout(300);
  await yourMove();
}
await move("f1", "a6");
await warning.waitFor({ timeout: 60000 });
const text = await warning.innerText();
pass(/⚠/.test(text), `warning shown: ${JSON.stringify(text.split("\n")[0])}`);
pass((await page.getByText("Opponent is thinking…").count()) === 0, "bot waits on the warning");
await page.screenshot({ path: "/work/out/p2a_1_warning.png" });
await page.getByRole("button", { name: "Take back" }).click();
await yourMove();
await page.waitForTimeout(500); // let the board animate the bishop home (180 ms)
pass((await sq("f1").locator("[data-piece]").count()) === 1, "take back: bishop home on f1");
pass((await warning.count()) === 0, "warning gone after take back");

// 4. Same blunder again, this time keep it: bot replies.
await move("f1", "a6");
await warning.waitFor({ timeout: 60000 });
await page.getByRole("button", { name: "Keep my move" }).click();
await yourMove();
pass((await warning.count()) === 0, "keep: warning gone, bot replied");
await page.screenshot({ path: "/work/out/p2a_2_after_keep.png" });

await browser.close();
