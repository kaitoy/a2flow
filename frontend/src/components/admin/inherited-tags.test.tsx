import { describe, expect, it } from "vitest";
import type { Tag } from "@/lib/api";
import { render, screen } from "@/test/test-utils";
import { InheritedTags, InheritedTagsField } from "./inherited-tags";

const TAG: Tag = {
  id: "tag-1",
  tenantId: "tenant-1",
  name: "production",
  color: "rose",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const BY_ID = new Map([[TAG.id, TAG]]);

describe("InheritedTags", () => {
  it("renders one chip per inherited tag", () => {
    render(<InheritedTags tagIds={["tag-1"]} byId={BY_ID} />);
    expect(screen.getByText("production")).toBeInTheDocument();
  });

  it("renders nothing when no tag is inherited", () => {
    const { container } = render(<InheritedTags tagIds={[]} byId={BY_ID} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("InheritedTagsField", () => {
  it("labels the section and explains where the tags come from", () => {
    render(<InheritedTagsField tagIds={["tag-1"]} byId={BY_ID} />);
    expect(screen.getByText("Tags from groups")).toBeInTheDocument();
    expect(screen.getByText("production")).toBeInTheDocument();
    expect(screen.getByText(/Granted by group membership/)).toBeInTheDocument();
  });

  it("says so when the user belongs to no tag-carrying group", () => {
    render(<InheritedTagsField tagIds={[]} byId={BY_ID} />);
    expect(
      screen.getByText("This user belongs to no group that carries a tag.")
    ).toBeInTheDocument();
  });
});
