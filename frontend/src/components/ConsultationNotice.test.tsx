import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConsultationNotice } from "./ConsultationNotice";

describe("ConsultationNotice", () => {
  it("says where a question goes while the session awaits a decision", () => {
    render(<ConsultationNotice />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "A question you send now opens a consultation"
    );
  });
});
