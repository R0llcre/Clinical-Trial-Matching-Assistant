import { expect, test } from "@playwright/test";

test.describe("Patients hub flow", () => {
  test("lists patients, creates a patient, and runs a match from patient detail", async ({
    page,
  }) => {
    await page.goto("/patients");

    await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Breast Cancer" })
    ).toBeVisible();

    await page.getByRole("link", { name: "New patient" }).first().click();
    await expect(page).toHaveURL(/\/patients\/new$/);

    await expect(page.getByRole("heading", { name: "New patient" })).toBeVisible();
    await page.getByLabel("Age").fill("45");
    await page.getByLabel("Sex").selectOption("female");
    await page.getByLabel("Conditions / diagnoses").fill("Breast Cancer");

    await page.getByRole("button", { name: "Create patient" }).click();

    await expect(page).toHaveURL(/\/patients\/patient-demo-001$/);
    await expect(page.getByRole("heading", { name: "Breast Cancer" })).toBeVisible();

    await page.getByRole("link", { name: "Edit patient" }).click();
    await expect(page).toHaveURL(/\/patients\/patient-demo-001\/edit$/);
    await expect(page.getByRole("heading", { name: "Edit patient" })).toBeVisible();

    await page.getByLabel("Age").fill("46");
    await page.getByLabel("Lab name").fill("eosinophils");
    await page.getByLabel("Value").fill("150");
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page).toHaveURL(/\/patients\/patient-demo-001$/);
    await expect(page.getByText("Age 46")).toBeVisible();

    await page.getByRole("button", { name: "Run match" }).click();
    await expect(page).toHaveURL(/\/matches\/match-demo-001$/);
    await expect(page.getByRole("button", { name: /^Strong match/ })).toBeVisible();
  });
});
