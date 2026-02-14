import { expect, test } from "@playwright/test";

test.describe("Match results midwidth layout", () => {
  test.use({ viewport: { width: 900, height: 700 } });

  test("keeps trial preview on the right (no mobile dock)", async ({ page }) => {
    await page.goto("/matches/match-demo-001");

    await expect(
      page.getByRole("heading", { name: "Match match-demo-001" })
    ).toBeVisible();

    const preview = page.getByRole("complementary", { name: "Trial preview" });
    await expect(preview).toBeVisible();

    await expect(page.getByRole("button", { name: "Open trial preview" })).toHaveCount(0);

    const firstCard = page.locator(".result-card-v3").first();
    await expect(firstCard).toBeVisible();

    const [cardBox, previewBox] = await Promise.all([
      firstCard.boundingBox(),
      preview.boundingBox(),
    ]);
    expect(cardBox).not.toBeNull();
    expect(previewBox).not.toBeNull();
    expect(previewBox!.x).toBeGreaterThan(cardBox!.x + cardBox!.width / 2);

    const cards = page.locator(".result-card-v3");
    const cardCount = await cards.count();
    for (let i = 0; i < cardCount; i += 1) {
      await cards.nth(i).getByRole("button", { name: "Show details" }).click();
    }

    // Reset scroll so we can validate sticky behavior from a known position.
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(100);

    const sticky = page.locator('aside[aria-label="Trial preview"] > div').first();
    await expect(sticky).toBeVisible();

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(100);
    await expect(sticky).toBeVisible();
    const afterScrollBox = await sticky.boundingBox();
    expect(afterScrollBox).not.toBeNull();
    // Sticky should pin the preview near the topbar offset instead of scrolling away.
    expect(afterScrollBox!.y).toBeLessThan(140);
  });
});
