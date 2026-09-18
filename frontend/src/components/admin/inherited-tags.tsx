/**
 * @module InheritedTags — Read-only display of the tags a user gets from their
 * group memberships.
 *
 * A user carries no tags of its own — every tag it shows is the union of its
 * groups' tags (see `models.tag` on the backend). Mirrors {@link InheritedRoles}
 * / {@link InheritedRolesField}, the analogous read-only display for
 * group-inherited roles, and reuses `tagChipItems` so a chip here renders
 * identically to the one in `tagsColumn`.
 */
"use client";

import { tagChipItems } from "@/components/admin/tag-columns";
import { ChipRow } from "@/components/ui/chip-row";
import type { Tag } from "@/lib/api";

/** Props for {@link InheritedTags} and {@link InheritedTagsField}. */
export interface InheritedTagsProps {
  /** Tag ids the user inherits from their groups; renders nothing when empty. */
  tagIds: string[];
  /** The tenant's tags keyed by id, from `useTags`. */
  byId: Map<string, Tag>;
}

/** Render group-inherited tags as chips. */
export function InheritedTags({ tagIds, byId }: InheritedTagsProps) {
  if (tagIds.length === 0) return null;
  return <ChipRow items={tagChipItems(tagIds, byId)} title="Tags" />;
}

/**
 * The same chips under a labelled heading, for use inside a form column
 * alongside {@link InheritedRolesField}.
 */
export function InheritedTagsField({ tagIds, byId }: InheritedTagsProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">Tags from groups</span>
      {tagIds.length === 0 ? (
        <p className="text-xs text-on-surface-variant">
          This user belongs to no group that carries a tag.
        </p>
      ) : (
        <>
          <InheritedTags tagIds={tagIds} byId={byId} />
          <p className="text-xs text-on-surface-variant">
            Granted by group membership. Edit the groups below, or the group&apos;s tags, to change
            these.
          </p>
        </>
      )}
    </div>
  );
}
