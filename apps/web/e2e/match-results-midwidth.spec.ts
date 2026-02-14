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

    await firstCard.getByRole("button", { name: "Show details" }).click();
    await page.evaluate(() => window.scrollBy(0, 1200));
    await expect(preview).toBeVisible();
  });
});

