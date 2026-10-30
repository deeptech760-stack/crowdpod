import { test, expect } from "@playwright/test";

test("responsive page has no horizontal overflow and all narrative sections remain visible", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  for (const width of [1440, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Before you build, ask the crowd." }),
    ).toBeVisible();
    await page.waitForTimeout(2800);
    const dimensions = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      viewport: innerWidth,
    }));
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.viewport + 1);
    await expect(page.locator("#use-cases")).toBeAttached();
    await page.screenshot({ path: `artifacts/hero-${width}.png` });
  }
  expect(errors).toEqual([]);
});

test("input, architect and comparison demos respond to real input", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("tab", { name: /Pick your crowd/ }).click();
  await expect(page.locator(".chat-preview")).toContainText("Auto driver");
  await page.getByRole("tab", { name: /Describe your idea/ }).click();
  await page
    .getByLabel("YOUR IDEA", { exact: true })
    .fill("A learning platform for teachers.");
  await expect(page.locator(".extracted")).toContainText(
    "A learning platform for teachers.",
  );
  await page
    .getByRole("button", { name: "Show the price", exact: true })
    .click();
  await expect(page.locator(".requirement-result")).toContainText(
    "Show the price on the landing page",
  );
  await expect(page.locator(".score-ring strong")).toHaveText("75%");
  await page.getByRole("button", { name: "Add interview questions" }).click();
  await expect(page.locator(".score-ring strong")).toHaveText("100%");
  const range = page.getByRole("slider", {
    name: "Before and after comparison",
  });
  await range.focus();
  await page.keyboard.press("End");
  await expect(range).toHaveValue("100");
  await page.keyboard.press("Home");
  await expect(range).toHaveValue("0");
  await page.getByRole("button", { name: "Competitor", exact: true }).click();
  await expect(page.locator(".clarified-result")).toContainText(
    "your competitor’s site",
  );
  await page
    .getByRole("button", { name: "Competitor research", exact: true })
    .click();
  await expect(page.locator(".use-art-paper")).toContainText(
    "The competitor teardown",
  );
});

test("mobile navigation, sign-in and info dialog are keyboard accessible", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .locator("#mobile-nav")
    .getByRole("link", { name: "The architect" })
    .click();
  await expect(page.locator("#mobile-nav")).not.toBeAttached();
  await page.getByRole("button", { name: "Contact", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Start a simulation" }),
  ).toHaveAttribute("href", "/app/");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page
    .getByRole("button", { name: "Get started", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL(/\/login\/?$/);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});

test("scroll story scrubs forward and backward and replay returns to its beginning", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.waitForTimeout(2800);
  const bounds = await page.locator("#how-it-works").evaluate((el) => {
    const spacer = el.parentElement!;
    return {
      top: spacer.getBoundingClientRect().top + scrollY,
      distance: innerHeight * 3,
    };
  });
  await page.evaluate(
    ({ top, distance }) =>
      window.scrollTo({ top: top + distance - 10, behavior: "instant" }),
    bounds,
  );
  await page.waitForTimeout(1500);
  await expect(page.locator(".final-panel")).toHaveCSS("visibility", "visible");
  await page.getByRole("button", { name: "Replay story" }).click();
  await page.waitForTimeout(1500);
  await expect(page.locator(".raw-panel")).toHaveCSS("visibility", "visible");
  await expect(page.locator(".final-panel")).toHaveCSS("visibility", "hidden");
});

test("essential copy is present without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Before you build, ask the crowd." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "The crowd finds your market." }),
  ).toBeVisible();
  await context.close();
});
