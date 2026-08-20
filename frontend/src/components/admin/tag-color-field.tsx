/**
 * @module TagColorField — palette-slot picker shared by the tag create and edit forms.
 *
 * Shared so the two forms stay in step, the same way {@link AgentSkillFields}
 * is shared between the agent-skill forms. The choice is a fixed vocabulary
 * rather than a free color value, so it is a select — paired with a live
 * {@link Chip} preview, centered in a generously padded space below the
 * select, because the slot names alone say nothing about what the tag will
 * look like on a list row.
 */
"use client";

import { ReadOnlyField } from "@/components/admin/read-only-field";
import { Chip } from "@/components/ui/chip";
import { Select } from "@/components/ui/select";
import type { TagColor } from "@/lib/api";
import { TAG_COLORS, tagColorLabel } from "@/lib/tag-palette";

/** Placeholder shown in the preview chip before the tag has a name. */
const PREVIEW_PLACEHOLDER = "tag";

/** Props for {@link TagColorField}. */
export interface TagColorFieldProps {
  /** Currently selected palette slot. */
  value: TagColor;
  /** Called with the next slot whenever the select changes. */
  onChange: (next: TagColor) => void;
  /**
   * Text shown in the preview chip — the tag's name as currently typed. Falls
   * back to a placeholder while the name field is empty.
   */
  previewLabel?: string;
  /** Renders the slot as a value instead of a select, for a viewer who cannot write. */
  readOnly?: boolean;
}

/**
 * Palette-slot select with a live chip preview.
 *
 * The preview reads the name field as it is typed rather than the saved value,
 * so the chip shown is the chip the user is about to create.
 */
export function TagColorField({
  value,
  onChange,
  previewLabel,
  readOnly = false,
}: TagColorFieldProps) {
  const label = previewLabel?.trim() || PREVIEW_PLACEHOLDER;

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">Color</span>
      {readOnly ? (
        <ReadOnlyField>{tagColorLabel(value)}</ReadOnlyField>
      ) : (
        <Select
          aria-label="Color"
          value={value}
          onChange={(next) => onChange(next as TagColor)}
          options={TAG_COLORS.map((color) => ({
            value: color,
            label: tagColorLabel(color),
          }))}
        />
      )}
      <div className="mt-5 flex items-center justify-center py-10">
        <Chip label={label} color={value} size="lg" />
      </div>
    </div>
  );
}
