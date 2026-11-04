// Browser check for the rating (PLAN D26). Run ONLY against the lctest stack (see
// spikes/compose.test.yml): it plays rated games, which would change a real rating. No LLM spend.
import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
const pass = (ok, msg) => console.log(`${ok ? "PASS" : "FAIL"} ${msg}`);
const has = async (t) => (await page.getByText(t).count()) > 0;

for (let i = 0; i < 30 && !(await page.goto("http://web:5173/").then(() => true, () => false)); i++)
  await page.waitForTimeout(2000);
await page.getByText("This game: casual · opponent 400").waitFor({ timeout: 60000 });
pass(true, "auto-started game is casual vs 400");
const ratingNumber = page.locator("span.text-2xl.tabular-nums");
pass((await ratingNumber.innerText()) === "400", `starting rating shown: ${await ratingNumber.innerText()}`);

await page.getByLabel("Rated").check();
await page.getByRole("button", { name: "New game (white)" }).click();
await page.getByText("This game: rated · opponent 400").waitFor({ timeout: 30000 });
pass(true, "rated game vs 400");
await page.getByRole("button", { name: "Resign" }).click();
await page.getByText("Rating 400 → 376").waitFor({ timeout: 10000 });
pass(true, "banner: Rating 400 → 376 (-24)");
await page.screenshot({ path: "/work/out/rating_1_banner.png" });

await page.getByRole("button", { name: "New game as white" }).click();
await page.getByText("This game: rated · opponent 376").waitFor({ timeout: 30000 });
pass(true, "next rated game's opponent follows the rating (376)");

await page.getByLabel("Rated").uncheck();
await page.getByRole("button", { name: "New game (white)" }).click();
await page.getByText("This game: casual · opponent 376").waitFor({ timeout: 30000 });
await page.getByRole("button", { name: "Resign" }).click();
await page.getByText("Casual game: rating unchanged").waitFor({ timeout: 10000 });
pass(true, "casual resignation leaves rating alone");
await page.reload();
await page.getByText("your rating").waitFor({ timeout: 30000 });
pass(!(await page.getByLabel("Rated").isChecked()), "Rated switch remembered (off) after reload");
await page.screenshot({ path: "/work/out/rating_2_panel.png" });
await browser.close();
