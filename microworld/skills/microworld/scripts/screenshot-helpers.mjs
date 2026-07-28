// Reusable screenshot-pass boilerplate: browser launch, one context per color
// scheme, console/page error logging. Shared so this mechanical part isn't
// hand-retyped (and silently drifting, e.g. stale hardcoded paths) per build.
// Requires: npm install playwright-core; uses the pre-installed Chromium.
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";

const CHROMIUM_PATH = "/opt/pw-browsers/chromium";

// steps: array of { name, click?, evaluate?, fullPage? }. Each step runs its
// click/evaluate action (if any), then screenshots to `${out}/${name}-${scheme}.png`.
// A step with neither action just screenshots the page as currently rendered
// (use this for the very first step, right after the page loads).
export async function shootBothThemes(url, out, steps) {
  mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROMIUM_PATH });
  try {
    for (const scheme of ["light", "dark"]) {
      const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, colorScheme: scheme });
      const page = await ctx.newPage();
      page.on("console", m => { if (m.type() === "error") console.log("CONSOLE ERROR:", m.text()); });
      page.on("pageerror", e => console.log("PAGE ERROR:", e.message));
      await page.goto(url);
      for (const step of steps) {
        if (step.click) await page.click(step.click);
        if (step.evaluate) await page.evaluate(step.evaluate);
        await page.screenshot({ path: `${out}/${step.name}-${scheme}.png`, fullPage: step.fullPage ?? false });
      }
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
}
