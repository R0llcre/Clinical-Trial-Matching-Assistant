import { expect, test } from "@playwright/test";

test.describe("Match and results flow", () => {
  test("runs match, opens results, and shows readable rule cards", async ({ page }) => {
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
    await expect(page.getByText("Breast Cancer · female · 45y")).toBeVisible();
    await expect(page.getByRole("link", { name: "Open patient" })).toHaveAttribute(
      "href",
      "/patients/patient-demo-001"
    );
    await expect(
      page.getByRole("button", { name: /^Strong match/ })
    ).toBeVisible();
    await page.getByRole("button", { name: /Potential/ }).click();

    await page
      .locator(".result-card-v3")
      .first()
      .getByRole("button", { name: "Show details" })
      .click();

    await expect(
      page.getByText("Requires lab value at least 150 cells/uL")
    ).toBeVisible();
    await expect(page.getByText("What to collect next")).toBeVisible();
    await expect(page.getByText("Add lab value: eosinophils")).toBeVisible();
    await expect(page.getByText("Include units and date measured.")).toBeVisible();

    const updateLink = page.getByRole("link", { name: "Update patient" }).first();
    await expect(updateLink).toHaveAttribute(
      "href",
      "/patients/patient-demo-001/edit?focus=eosinophils"
    );
    await updateLink.click();
    await expect(page).toHaveURL(/\/patients\/patient-demo-001\/edit\?focus=eosinophils$/);
    await expect(page.getByRole("heading", { name: "Edit patient" })).toBeVisible();

    await expect(page.getByText("c260529e-3104-47ac-95bd-4b7064be2a1f")).toHaveCount(0);
  });
});
