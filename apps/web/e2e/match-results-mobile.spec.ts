import { expect, test } from "@playwright/test";

test.describe("Match results mobile preview", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("shows a bottom dock and opens the trial preview drawer", async ({ page }) => {
    await page.goto("/match");

    await expect(
      page.getByRole("heading", { name: "Match a patient to clinical trials" })
    ).toBeVisible();

    await page.selectOption("#demo", {
      label: "Breast cancer (female, 45)",
    });

    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Next" }).click();

    await expect(page.locator(".match-card__title", { hasText: "Review" })).toBeVisible();
    await page.getByRole("button", { name: "Run match" }).click();

    await expect(page).toHaveURL(/\/matches\/match-demo-001$/);

    // Switch to Potential so the selected trial has UNKNOWN lab requirement.
    await page.getByRole("button", { name: /Potential/ }).click();

    const dock = page.getByRole("button", { name: "Open trial preview" });
    await expect(dock).toBeVisible();
    await dock.click();

    const drawer = page.getByRole("dialog", { name: "Trial preview" });
    await expect(drawer.getByText("Key issues")).toBeVisible();
    await expect(drawer.getByText("Add lab value: eosinophils")).toBeVisible();

    await drawer.getByRole("button", { name: "Show full checklist" }).click();

    await expect(page.getByRole("dialog", { name: "Trial preview" })).toHaveCount(0);
    await expect(
      page
        .locator("#result-NCT10000002")
        .getByText("Requires lab value at least 150 cells/uL")
    ).toBeVisible();

    await expect(page.getByText("c260529e-3104-47ac-95bd-4b7064be2a1f")).toHaveCount(0);
  });
});
