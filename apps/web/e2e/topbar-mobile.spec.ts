import { expect, test } from "@playwright/test";

test.describe("Topbar mobile navigation", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("does not overflow horizontally and nav drawer works", async ({ page }) => {
    await page.goto("/");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);

    const menuButton = page.getByRole("button", { name: "Menu" });
    await expect(menuButton).toBeVisible();
    await menuButton.click();

    const drawer = page.getByRole("dialog", { name: "Navigation" });
    await expect(drawer.getByRole("link", { name: "Patients" })).toBeVisible();
    await drawer.getByRole("link", { name: "Patients" }).click();

    await expect(page).toHaveURL(/\/patients/);
    await expect(page.getByRole("dialog", { name: "Navigation" })).toHaveCount(0);

    const overflowAfter = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth
    );
    expect(overflowAfter).toBeLessThanOrEqual(1);
  });
});

