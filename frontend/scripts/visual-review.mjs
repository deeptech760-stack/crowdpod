import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";

await mkdir("artifacts", { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  });
  await page.goto("http://127.0.0.1:3000");
  await page.evaluate(() => document.fonts.ready);
  for (const id of ["inputs", "features", "use-cases"]) {
    await page.locator(`#${id}`).screenshot({ path: `artifacts/${id}.png` });
  }
  await page.screenshot({
    path: "artifacts/full-page-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "artifacts/full-page-mobile.png",
    fullPage: true,
  });
  // The remote reference is inspected only; no assets or source are copied.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("https://wisprflow.ai/", {
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "artifacts/wispr-reference.png" });
  console.log(
    JSON.stringify(
      await page.evaluate(() => ({
        title: document.title,
        animatedElements: document.getAnimations().length,
        heading: document.querySelector("h1")?.textContent,
      })),
    ),
  );
} finally {
  await browser.close();
}
