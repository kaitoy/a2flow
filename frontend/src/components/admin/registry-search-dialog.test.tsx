import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { RegistrySearchDialog } from "@/components/admin/registry-search-dialog";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";

const BASE = "http://localhost:8000";

const WEATHER = {
  name: "io.example/weather",
  title: "Weather",
  description: "Weather lookups.",
  version: "1.2.0",
  url: "https://mcp.example.com/weather",
  headers: [{ name: "Authorization", isRequired: true, isSecret: true }],
};

const SEARCH = {
  name: "io.example/search",
  title: "Search",
  version: "2.0.0",
  url: "https://mcp.example.com/search",
};

function pageHandler(servers: unknown[], nextCursor: string | null = null) {
  return http.get(`${BASE}/api/v1/mcp-registry`, ({ request }) => {
    const cursor = new URL(request.url).searchParams.get("cursor");
    if (cursor === "more") {
      return envelope({ servers: [SEARCH], nextCursor: null });
    }
    return envelope({ servers, nextCursor });
  });
}

describe("RegistrySearchDialog", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <RegistrySearchDialog open={false} onClose={vi.fn()} onSelect={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("lists results and selects one via Use this", async () => {
    server.use(pageHandler([WEATHER]));
    const onSelect = vi.fn();
    const user = userEvent.setup();

    render(<RegistrySearchDialog open onClose={vi.fn()} onSelect={onSelect} />);

    await waitFor(() => expect(screen.getByText("Weather")).toBeInTheDocument());
    expect(screen.getByText("https://mcp.example.com/weather")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /use this/i }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ name: "io.example/weather" }));
  });

  it("shows an empty state when there are no results", async () => {
    server.use(pageHandler([]));
    render(<RegistrySearchDialog open onClose={vi.fn()} onSelect={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("No servers found")).toBeInTheDocument());
  });

  it("shows an error banner when the search fails", async () => {
    server.use(
      http.get(`${BASE}/api/v1/mcp-registry`, () => new HttpResponse(null, { status: 500 }))
    );
    render(<RegistrySearchDialog open onClose={vi.fn()} onSelect={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });

  it("loads the next page when Load more is clicked", async () => {
    server.use(pageHandler([WEATHER], "more"));
    const user = userEvent.setup();
    render(<RegistrySearchDialog open onClose={vi.fn()} onSelect={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("Weather")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /load more/i }));

    await waitFor(() => expect(screen.getByText("Search")).toBeInTheDocument());
    expect(screen.getByText("Weather")).toBeInTheDocument();
  });

  it("closes via the Cancel button", async () => {
    server.use(pageHandler([WEATHER]));
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RegistrySearchDialog open onClose={onClose} onSelect={vi.fn()} />);

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
