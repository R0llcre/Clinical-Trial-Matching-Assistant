import { expect, test } from "@playwright/test";

test.describe("Browse flow", () => {
  test("applies filters, updates URL, and clears back to default list", async ({ page }) => {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: "Browse trials" })
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Targeted Therapy in HER2+ Breast Cancer" })
    ).toBeVisible();

    await page.getByLabel("Condition").fill("Asthma");
    await page.getByRole("button", { name: "Search" }).click();

    await expect(page).toHaveURL(/condition=Asthma/);
    await expect(
      page.getByRole("link", {
        name: "Biologic Maintenance Study for Moderate Asthma",
      })
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Targeted Therapy in HER2+ Breast Cancer" })
    ).toHaveCount(0);

    await page.getByRole("button", { name: "Clear all" }).click();

    await expect(page).not.toHaveURL(/condition=/);
    await expect(
      page.getByRole("link", { name: "Targeted Therapy in HER2+ Breast Cancer" })
    ).toBeVisible();
  });
});
