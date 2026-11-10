import { test } from "@e2e-dev/web";
import { expect } from "e2e";
import { loginAsAdmin } from "./login.ts";

test("an admin creates, edits, and deletes a tag", async ({ app, screen }) => {
  // Unique per attempt: a CI retry reuses the same database.
  const name = `e2e-tag-${Date.now()}`;
  const description = "Edited by the e2e suite";
  const row = screen.getByTestId("data-table-row").filter({ hasText: name });

  await loginAsAdmin(app, screen);
  await app.open("/tags");

  await screen.getByTestId("admin-page-header-add").click();
  await screen.getByTestId("tag-name").fill(name);
  await screen.getByTestId("tag-save").click();
  await expect(row).toBeVisible({ timeout: 15_000 });

  await row.getByTestId("tag-link").click();
  await screen.getByTestId("tag-description").fill(description);
  await screen.getByTestId("tag-save").click();
  await expect(row).toContainText(description, { timeout: 15_000 });

  await row.getByTestId("tag-link").click();
  await screen.getByTestId("tag-delete").click();
  await screen.getByTestId("confirm-dialog-confirm").click();
  await expect(screen.getByTestId("admin-page-header-add")).toBeVisible({ timeout: 15_000 });
  await expect(row).toHaveCount(0);
});
