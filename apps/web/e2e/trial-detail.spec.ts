import { expect, test } from "@playwright/test";

test.describe("Trial detail flow", () => {
  test("renders eligibility and parsed rules in readable structure", async ({ page }) => {
    await page.goto("/trials/NCT10000001");

    await expect(
      page.getByRole("heading", {
        name: "Targeted Therapy in HER2+ Breast Cancer",
      })
    ).toBeVisible();

    await page.getByRole("tab", { name: "Eligibility" }).click();
    await expect(
      page.getByText("Participants must be 18 years or older.")
    ).toBeVisible();

    const showFull = page.getByRole("button", {
      name: "Show full eligibility",
    });
    await expect(showFull).toBeVisible();
    await showFull.click();
    await expect(page.getByText("Additional Notes:")).toBeVisible();

    await page.getByRole("tab", { name: /Parsed criteria/i }).click();
    await expect(page.getByText("Filter by field")).toBeVisible();
    const readableRule = page.getByRole("button", {
      name: /Requires age at least 18 years/i,
    });
    await expect(readableRule).toBeVisible();

    await page.getByRole("button", { name: /^Lab\s+\d+$/ }).click();
    await expect(
      page.getByRole("button", { name: /Requires age at least 18 years/i })
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: /Requires lab value/i })
    ).toBeVisible();

    await page.getByRole("button", { name: /^All\s+\d+$/ }).click();
    await readableRule.click();
    await expect(page.getByText("Evidence")).toBeVisible();
    await expect(page.getByText("field: age · operator: >= · value: 18 years")).toBeVisible();
  });
});
