import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InitiatorResumeNotice, RESUME_MESSAGE } from "./InitiatorResumeNotice";

describe("InitiatorResumeNotice", () => {
  it("lets the initiator resume by sending a chat message", () => {
    const onSend = vi.fn();
    render(<InitiatorResumeNotice taskTitle="Rotate secret" canResume onSend={onSend} />);

    expect(screen.getByRole("status")).toHaveTextContent("“Rotate secret” will ask you questions");
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));

    expect(onSend).toHaveBeenCalledWith(RESUME_MESSAGE);
  });

  it("only tells anyone else what the session waits for", () => {
    render(<InitiatorResumeNotice taskTitle={null} canResume={false} onSend={vi.fn()} />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "The next task is waiting for the person who started this run"
    );
    expect(screen.queryByRole("button")).toBeNull();
  });
});
