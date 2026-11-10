import type { App, Screen } from "e2e";
import { expect } from "e2e";

/** The Default tenant admin's password; e2e/start.sh seeds it as ADMIN_PASSWORD. */
export const ADMIN_PASSWORD = "e2e-admin-pass-123";

/**
 * Signs in as `admin` in the seeded Default tenant and waits until the sign-in
 * form is gone, so the session cookie is set before the test opens a page.
 */
export async function loginAsAdmin(app: App, screen: Screen): Promise<void> {
  await app.open("/login");
  await screen.getByTestId("login-username").fill("admin");
  await screen.getByTestId("login-tenant").fill("default");
  await screen.getByTestId("login-password").fill(ADMIN_PASSWORD);
  await screen.getByTestId("login-submit").click();
  await expect(screen.getByTestId("login-submit")).toBeHidden({ timeout: 15_000 });
}
