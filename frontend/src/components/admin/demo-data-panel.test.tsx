import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { DemoDataPanel } from "./demo-data-panel";

const PATH = "http://localhost:8000/api/v1/demo-data";

describe("DemoDataPanel", () => {
  it("shows the status, with Clear disabled while nothing is loaded", async () => {
    render(<DemoDataPanel />);
    expect(await screen.findByTestId("demo-data-status")).toHaveTextContent(
      "Not loaded in this tenant."
    );
    expect(screen.getByTestId("demo-data-load")).toBeEnabled();
    expect(screen.getByTestId("demo-data-clear")).toBeDisabled();
  });

  it("loads only after the confirmation", async () => {
    const loaded = vi.fn(() => envelope({ loaded: true, keptCount: 0 }));
    server.use(http.post(PATH, loaded));
    const user = userEvent.setup();
    const { store } = render(<DemoDataPanel />);

    await user.click(await screen.findByTestId("demo-data-load"));
    expect(loaded).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("confirm-dialog-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("demo-data-status")).toHaveTextContent("Loaded in this tenant.")
    );
    expect(loaded).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("demo-data-clear")).toBeEnabled();
    expect(store.getState().toast.items.map((t) => t.message)).toContain("Demo data loaded");
  });

  it("clears, and says how many records were kept", async () => {
    server.use(
      http.get(PATH, () => envelope({ loaded: true, keptCount: 0 })),
      http.delete(PATH, () => envelope({ loaded: true, keptCount: 2 }))
    );
    const user = userEvent.setup();
    const { store } = render(<DemoDataPanel />);

    await user.click(await screen.findByTestId("demo-data-clear"));
    await user.click(screen.getByTestId("confirm-dialog-confirm"));

    await waitFor(() =>
      expect(store.getState().toast.items.map((t) => t.message)).toContain(
        "Demo data cleared. 2 records were kept because other records use them."
      )
    );
  });

  it("renders nothing when the status cannot be read", async () => {
    const read = vi.fn(() => envelopeErr("FORBIDDEN", "Forbidden", 403));
    server.use(http.get(PATH, read));
    const { container } = render(<DemoDataPanel />);
    await waitFor(() => expect(read).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
