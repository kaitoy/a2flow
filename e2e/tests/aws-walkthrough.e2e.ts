import { test } from "@e2e-dev/web";
import { expect } from "e2e";
import { loginAsAdmin } from "./login.ts";

/**
 * The manual's AWS walkthrough on its no-account path: the demo developer
 * generates a workflow from the demo skill and runs the draft with the seeded
 * tool mocks, so nothing reaches AWS or waits on an approver. The backend's
 * scripted LLM (backend/scripts/e2e_server.py) plays both agents; its closing
 * message is FINAL_TEXT there.
 *
 * Text matches ignore case: e2e compares rendered text, and the GUI capitalizes
 * statuses and upper-cases the "Acting as" chip with CSS.
 */
test(
  "the demo AWS EC2 launch plays through with tool mocks",
  { timeout: 300_000 },
  async ({ app, screen, browser }) => {
    const row = (text: string) => screen.getByTestId("data-table-row").filter({ hasText: text });

    await loginAsAdmin(app, screen);

    // Act as the demo developer: only a developer may run a draft.
    await app.open("/users");
    await row("demo-aws-developer").getByTestId("user-impersonate").click();
    await screen.getByTestId("confirm-dialog-confirm").click();
    await expect(screen.getByTestId("impersonation-indicator")).toContainText(
      /demo-aws-developer/i,
      { timeout: 15_000 }
    );

    // The skill is cloned from GitHub in the background after startup.
    await app.open("/agent-skills");
    const skill = row("Demo AWS EC2 Launch");
    await expect
      .poll(
        async () => {
          await browser.reload();
          await expect(skill).toBeVisible({ timeout: 15_000 });
          return (await skill.getByTestId("agent-skill-status").textContent())?.toLowerCase();
        },
        { timeout: 120_000, interval: 3_000 }
      )
      .toBe("ready");

    await skill.getByTestId("agent-skill-generate").click();
    await screen
      .getByTestId("generate-workflow-prompt")
      .fill("Launch an EC2 instance after approval from the Demo Approvers group.");
    await screen.getByTestId("generate-workflow-submit").click();
    await expect(screen.getByTestId("workflow-status")).toHaveText(/^draft$/i, { timeout: 120_000 });

    await screen.getByTestId("workflow-run").click();
    await screen.getByTestId("run-workflow-mock-aws___call_aws").check();
    await screen.getByTestId("run-workflow-mock-request_approval").check();
    await screen.getByTestId("run-workflow-submit").click();

    await expect(
      screen.getByTestId("chat-message-assistant").filter({ hasText: "Launched the EC2 instance." })
    ).toBeVisible({ timeout: 120_000 });
    await expect(
      screen.getByTestId("workflow-task-status").filter({ hasText: /^completed$/i })
    ).toHaveCount(2, { timeout: 30_000 });

    await app.open("/workflow-executions");
    // Newest first, so a CI retry's run is the first row.
    await expect(screen.getByTestId("workflow-execution-status").first()).toHaveText(/^completed$/i, {
      timeout: 15_000,
    });

    await screen.getByTestId("impersonation-stop").click();
    await expect(screen.getByTestId("impersonation-indicator")).toBeHidden({ timeout: 15_000 });
  }
);
