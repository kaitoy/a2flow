import { describe, expect, it } from "vitest";
import { loadMessages } from "@/i18n/load";
import { createTranslator } from "@/i18n/translate";
import type { Notification } from "@/lib/api";
import { notificationText } from "./notification-text";

const ja = createTranslator("ja", await loadMessages("ja"));

function notification(fields: Partial<Notification>): Notification {
  return { title: "Stored title", body: "Stored body", ...fields } as Notification;
}

describe("notificationText", () => {
  it("translates fixed wording", () => {
    expect(notificationText(notification({ type: "workflow_draft_ready" }), ja).title).toBe(
      "ワークフローの下書きができました"
    );
  });

  it("fills values from params", () => {
    const text = notificationText(
      notification({ type: "execution_completed", params: { count: 3 } }),
      ja
    );
    expect(text.body).toContain("3");
    expect(text.body).not.toBe("Stored body");

    const asking = notificationText(
      notification({ type: "elicitation_request", params: { taskTitle: "Deploy" } }),
      ja
    );
    expect(asking.title).toContain("Deploy");
  });

  it("keeps the stored text where a row predates params", () => {
    expect(notificationText(notification({ type: "execution_completed" }), ja).body).toBe(
      "Stored body"
    );
    expect(notificationText(notification({ type: "elicitation_request" }), ja).title).toBe(
      "Stored title"
    );
  });

  it("keeps agent-written and failure text as stored", () => {
    expect(notificationText(notification({ type: "approval_request" }), ja)).toEqual({
      title: "Stored title",
      body: "Stored body",
    });
    expect(notificationText(notification({ type: "workflow_generation_failed" }), ja).body).toBe(
      "Stored body"
    );
  });
});
