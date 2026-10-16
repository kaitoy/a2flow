import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { KNOWLEDGE_SOURCE_READY } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { KnowledgeSourcesPanel } from "./knowledge-sources-panel";

const SOURCES_URL = "http://localhost:8000/api/v1/knowledge-bases/:kbId/sources";

describe("KnowledgeSourcesPanel", () => {
  it("lists each source with its state, title, and failure reason", async () => {
    render(<KnowledgeSourcesPanel knowledgeBaseId="kb-1" canEdit />);
    expect(await screen.findByText("vpn.pdf")).toBeInTheDocument();
    expect(screen.getByText("VPN guide")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://example.com/handbook" })).toHaveAttribute(
      "href",
      "https://example.com/handbook"
    );
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("https://example.com/handbook answered HTTP 404")).toBeInTheDocument();
  });

  it("registers a URL and reloads the list", async () => {
    const posted = vi.fn();
    server.use(
      http.post(`${SOURCES_URL}/url`, async ({ request }) => {
        posted(await request.json());
        return envelope({ ...KNOWLEDGE_SOURCE_READY, status: "pending" }, 201);
      })
    );
    const user = userEvent.setup();
    render(<KnowledgeSourcesPanel knowledgeBaseId="kb-1" canEdit />);
    await screen.findByText("vpn.pdf");

    await user.type(screen.getByLabelText("Web page URL"), "https://example.com/new");
    await user.click(screen.getByRole("button", { name: "Add URL" }));

    await waitFor(() => expect(posted).toHaveBeenCalledWith({ url: "https://example.com/new" }));
    expect(screen.getByLabelText("Web page URL")).toHaveValue("");
  });

  it("uploads each picked document", async () => {
    const uploaded = vi.fn();
    server.use(
      http.post(`${SOURCES_URL}/file`, async ({ request }) => {
        const file = (await request.formData()).get("file") as File;
        uploaded(file.name);
        return envelope({ ...KNOWLEDGE_SOURCE_READY, status: "pending" }, 201);
      })
    );
    const user = userEvent.setup();
    const { container } = render(<KnowledgeSourcesPanel knowledgeBaseId="kb-1" canEdit />);
    await screen.findByText("vpn.pdf");

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, [
      new File(["a"], "a.pdf", { type: "application/pdf" }),
      new File(["b"], "b.txt", { type: "text/plain" }),
    ]);

    await waitFor(() => expect(uploaded.mock.calls).toEqual([["a.pdf"], ["b.txt"]]));
  });

  it("removes a source only after confirmation", async () => {
    const removed = vi.fn();
    server.use(
      http.delete(`${SOURCES_URL}/:sourceId`, ({ params }) => {
        removed(params.sourceId);
        return envelope({ ...KNOWLEDGE_SOURCE_READY, status: "removing" });
      })
    );
    const user = userEvent.setup();
    render(<KnowledgeSourcesPanel knowledgeBaseId="kb-1" canEdit />);
    await screen.findByText("vpn.pdf");

    await user.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    expect(removed).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(removed).toHaveBeenCalledWith("src-a"));
  });

  it("re-reads a source", async () => {
    const reread = vi.fn();
    server.use(
      http.post(`${SOURCES_URL}/:sourceId/reingest`, ({ params }) => {
        reread(params.sourceId);
        return envelope({ ...KNOWLEDGE_SOURCE_READY, status: "pending" });
      })
    );
    const user = userEvent.setup();
    render(<KnowledgeSourcesPanel knowledgeBaseId="kb-1" canEdit />);
    await screen.findByText("vpn.pdf");

    await user.click(screen.getAllByRole("button", { name: "Read again" })[1]);

    await waitFor(() => expect(reread).toHaveBeenCalledWith("src-b"));
  });

  it("offers no controls to a viewer who cannot edit", async () => {
    render(<KnowledgeSourcesPanel knowledgeBaseId="kb-1" canEdit={false} />);
    await screen.findByText("vpn.pdf");
    expect(screen.queryByLabelText("Web page URL")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload documents/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("reports when background work settles", async () => {
    let calls = 0;
    server.use(
      http.get(SOURCES_URL, () => {
        calls += 1;
        return envelope([
          { ...KNOWLEDGE_SOURCE_READY, status: calls === 1 ? "ingesting" : "ready" },
        ]);
      })
    );
    const onSettled = vi.fn();
    render(<KnowledgeSourcesPanel knowledgeBaseId="kb-1" canEdit onSettled={onSettled} />);

    expect(await screen.findByText("Reading")).toBeInTheDocument();
    await waitFor(() => expect(onSettled).toHaveBeenCalledOnce(), { timeout: 5000 });
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });
});
