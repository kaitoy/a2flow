/** @module AvatarDialog — Modal avatar editor for the signed-in user (uploaded image and generated default). */
"use client";

import { useEffect, useRef, useState } from "react";
import { Avatar, type AvatarUser } from "@/components/ui/avatar";
import { AvatarField } from "@/components/ui/avatar-field";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { type AvatarConfig, updateUser } from "@/lib/api";
import { avatarPalette, DEFAULT_AVATAR_PALETTE } from "@/lib/avatar-palette";
import { setUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";

/** Props for {@link AvatarDialog}. */
export interface AvatarDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Called on Close, Escape, or a backdrop click. */
  onClose: () => void;
  /** The signed-in user whose avatar is being edited. */
  user: AvatarUser;
}

/**
 * The signed-in user's avatar editor, opened from the avatar in
 * {@link import("./profile-hero").ProfileHero}.
 *
 * The top section uploads or removes a custom image (which takes priority
 * everywhere the avatar is shown); the lower section customizes the generated
 * avatar by editing the color palette it is drawn from, used when no image is
 * uploaded. Both an upload/removal and a saved {@link AvatarConfig} refresh the
 * auth slice, so every avatar across the app — the hero behind this dialog and
 * the header button above it — updates immediately.
 *
 * An image upload commits as soon as its own Upload button is pressed; the
 * palette is the only unsaved state the dialog holds, which is why Save and
 * Reset speak about the palette and not about the dialog as a whole. Both
 * committing paths — a finished upload, and a saved palette — close the dialog
 * rather than celebrating in place: the result is the avatar in the hero behind
 * it, and that is where the eye should land.
 *
 * Reset only rewinds the swatches; nothing reaches the server until Save. That
 * makes Close a real discard, so the palette is re-seeded from the stored
 * config every time the dialog opens.
 */
export function AvatarDialog({ open, onClose, user }: AvatarDialogProps) {
  const dispatch = useAppDispatch();

  const [colors, setColors] = useState<string[]>(() => avatarPalette(user.avatarConfig));

  // No `done` stage: on success the dialog closes, so a "Saved!" label and its
  // wiggle would play on a button that is already sliding off screen.
  const action = useAsyncAction({ showDone: false });
  const [error, setError] = useState<string | null>(null);

  // Reopening discards whatever was left unsaved last time. This fires on the
  // closed→open transition only, never on any later change to the stored
  // config: an upload refreshes the auth user mid-edit, and re-seeding on that
  // would wipe swatches the user is still working on.
  const wasOpen = useRef(open);
  useEffect(() => {
    if (open && !wasOpen.current) {
      setColors(avatarPalette(user.avatarConfig));
      setError(null);
    }
    wasOpen.current = open;
  }, [open, user.avatarConfig]);

  // The live preview mirrors the real Avatar render with the in-progress palette.
  const previewUser: AvatarUser = {
    ...user,
    avatarUpdatedAt: null,
    avatarConfig: { colors },
  };

  function setColorAt(index: number, value: string) {
    setColors((prev) => prev.map((color, i) => (i === index ? value : color)));
  }

  async function handleSave() {
    setError(null);
    // A palette identical to the application default is stored as `null` rather
    // than as an explicit copy of it — that is what Reset means, and it keeps a
    // user who has customized nothing off the custom-palette path entirely.
    const config: AvatarConfig | null = isDefaultPalette(colors) ? null : { colors };
    try {
      await action.run(async () => {
        dispatch(setUser(await updateUser(user.id, { avatarConfig: config })));
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save avatar");
    }
  }

  function handleReset() {
    setError(null);
    setColors([...DEFAULT_AVATAR_PALETTE]);
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId="avatar-dialog"
      title="Edit avatar"
      description="Upload an image, or tune the colors your generated avatar is drawn from."
      size="md"
      scrollable
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={action.inFlight}>
            Close
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={action.inFlight}
            status={action.status}
            pendingLabel="Saving…"
          >
            Save
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-6 overflow-y-auto">
        <AvatarField
          label="Uploaded image"
          user={user}
          onChange={(updated) => dispatch(setUser(updated))}
          onUploaded={onClose}
        />

        <div className="flex flex-col gap-4 border-t border-glass-border pt-6">
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-on-surface">Generated avatar</h3>
            <p className="text-xs text-on-surface-variant">Used when no image is uploaded.</p>
          </div>

          <div className="flex flex-wrap items-center gap-6">
            <Avatar user={previewUser} size={96} />
            <PalettePicker colors={colors} onChange={setColorAt} />
          </div>

          <div className="flex flex-col items-end gap-2">
            {error && <p className="text-xs text-error">{error}</p>}
            {/* Purely local — it rewinds the swatches and leaves the commit to
                Save, so it carries no submitting-button lifecycle at all. */}
            <Button variant="ghost" onClick={handleReset} disabled={action.inFlight}>
              Reset to default
            </Button>
          </div>
        </div>
      </div>
    </Dialog>
  );
}

/**
 * Whether a palette is indistinguishable from the application default.
 *
 * Compared case-insensitively because `<input type="color">` normalizes its
 * value to lowercase hex while {@link DEFAULT_AVATAR_PALETTE} is written in the
 * casing `avatar-palette.ts` uses — a swatch the user never touched would
 * otherwise read as an edit.
 *
 * @param colors - The palette currently held by the dialog.
 * @returns True when it matches the default slot for slot.
 */
function isDefaultPalette(colors: string[]): boolean {
  return (
    colors.length === DEFAULT_AVATAR_PALETTE.length &&
    colors.every((color, i) => color.toLowerCase() === DEFAULT_AVATAR_PALETTE[i].toLowerCase())
  );
}

/** Props for {@link PalettePicker}. */
interface PalettePickerProps {
  /** The palette being edited, in the order the renderer consumes it. */
  colors: string[];
  /** Called with the slot index and its new hex value when a swatch changes. */
  onChange: (index: number, value: string) => void;
}

/**
 * A row of color inputs, one per palette slot. The renderer picks slots by
 * hashing the username seed, so the swatches are labeled by position rather
 * than by the feature they end up tinting.
 */
function PalettePicker({ colors, onChange }: PalettePickerProps) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="text-label-caps">Palette</legend>
      <div className="flex flex-wrap gap-4">
        {colors.map((color, index) => (
          <label
            // biome-ignore lint/suspicious/noArrayIndexKey: the palette is a fixed-length ordered list of positional slots that is never reordered or resized, and two slots may hold the same color, so the index is the only stable identity.
            key={`palette-slot-${index + 1}`}
            className="flex items-center gap-2 text-sm text-on-surface"
          >
            <input
              type="color"
              value={color}
              onChange={(e) => onChange(index, e.target.value)}
              aria-label={`Palette color ${index + 1}`}
              className="h-8 w-8 cursor-pointer rounded-md border border-glass-border bg-transparent"
            />
            {index + 1}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
