import { expect, test } from "@playwright/test"
import { createUser } from "./utils/privateApi"
import { randomEmail, randomPassword } from "./utils/random"
import { logInUser } from "./utils/user"

test("Countries page is accessible and shows correct title", async ({
  page,
}) => {
  await page.goto("/items")
  await expect(page.getByRole("heading", { name: "Countries" })).toBeVisible()
  await expect(page.getByText("Create and manage countries")).toBeVisible()
})

test("Add Country button is visible", async ({ page }) => {
  await page.goto("/items")
  await expect(page.getByRole("button", { name: "Add Country" })).toBeVisible()
})

test.describe("Countries management", () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  let email: string
  const password = randomPassword()

  test.beforeAll(async () => {
    email = randomEmail()
    await createUser({ email, password })
  })

  test.beforeEach(async ({ page }) => {
    await logInUser(page, email, password)
    await page.goto("/items")
  })

  test("Create a new country successfully", async ({ page }) => {
    await page.getByRole("button", { name: "Add Country" }).click()
    await page.getByLabel("Country name").fill("Bolivia")
    await page.getByLabel("ISO numeric").fill("068")
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("Country created successfully")).toBeVisible()
    await expect(page.getByText("Bolivia")).toBeVisible()
  })

  test("Cancel country creation", async ({ page }) => {
    await page.getByRole("button", { name: "Add Country" }).click()
    await page.getByLabel("ISO numeric").fill("068")
    await page.getByRole("button", { name: "Cancel" }).click()

    await expect(page.getByRole("dialog")).not.toBeVisible()
  })

  test.describe("Edit and Delete", () => {
    let countryName: string

    test.beforeEach(async ({ page }) => {
      countryName = "Bolivia"

      await page.getByRole("button", { name: "Add Country" }).click()
      await page.getByLabel("Country name").fill(countryName)
      await page.getByLabel("ISO numeric").fill("068")
      await page.getByRole("button", { name: "Save" }).click()
      await expect(page.getByText("Country created successfully")).toBeVisible()
      await expect(page.getByRole("dialog")).not.toBeVisible()
    })

    test("Edit a country successfully", async ({ page }) => {
      const itemRow = page.getByRole("row").filter({ hasText: countryName })
      await itemRow.getByRole("button").last().click()
      await page.getByRole("menuitem", { name: "Edit Country" }).click()

      await page.getByLabel("ISO numeric").fill("069")
      await page.getByRole("button", { name: "Save" }).click()

      await expect(page.getByText("Country updated successfully")).toBeVisible()
      await expect(page.getByText("069")).toBeVisible()
    })

    test("Delete a country successfully", async ({ page }) => {
      const itemRow = page.getByRole("row").filter({ hasText: countryName })
      await itemRow.getByRole("button").last().click()
      await page.getByRole("menuitem", { name: "Delete Country" }).click()

      await page.getByRole("button", { name: "Delete" }).click()

      await expect(
        page.getByText("The country was deleted successfully"),
      ).toBeVisible()
      await expect(page.getByText(countryName)).not.toBeVisible()
    })
  })
})

test.describe("Countries empty state", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Shows empty state message when no countries exist", async ({
    page,
  }) => {
    const email = randomEmail()
    const password = randomPassword()
    await createUser({ email, password })
    await logInUser(page, email, password)

    await page.goto("/items")

    await expect(
      page.getByText("You do not have any countries yet"),
    ).toBeVisible()
    await expect(
      page.getByText("Add a new country to get started"),
    ).toBeVisible()
  })
})
