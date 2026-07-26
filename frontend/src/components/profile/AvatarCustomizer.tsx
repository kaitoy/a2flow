/** @module AvatarCustomizer — Editable avatar section of the profile page (uploaded image and generated default). */
"use client";

import { useState } from "react";
import { Avatar, type AvatarUser } from "@/components/ui/avatar";
import { AvatarField } from "@/components/ui/avatar-field";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { type AvatarConfig, updateUser } from "@/lib/api";
import { avatarPalette, DEFAULT_AVATAR_PALETTE } from "@/lib/avatar-palette";
import { setUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";

/** Props for {@link AvatarCustomizer}. */
interface AvatarCustomizerProps {
  /** The signed-in user whose generated avatar is being customized. */
  user: AvatarUser;
}

/**
 * The one editable section of the profile page: a signed-in user's avatar. The
 * top part uploads or removes a custom image (which takes priority everywhere
 * it is shown); the lower part customizes the generated avatar by editing the
 * color palette it is drawn from, used when no image is uploaded. Both an
 * upload/removal and a saved {@link AvatarConfig} refresh the auth slice so
 * every avatar across the app (including the header button) updates
 * immediately.
 *
 * Renders as a self-contained card; the surrounding page owns the page title
 * and the column layout.
 */
export function AvatarCustomizer({ user }: AvatarCustomizerProps) {
  const dispatch = useAppDispatch();

  const [colors, setColors] = useState<string[]>(() => avatarPalette(user.avatarConfig));

  const action = useAsyncAction();
  // Which button triggered the in-flight request, so only that button shows the
  // pending/done label while both stay disabled.
  const [pendingAction, setPendingAction] = useState<"save" | "reset" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The live preview mirrors the real Avatar render with the in-progress palette.
  const previewUser: AvatarUser = {
    ...user,
    avatarUpdatedAt: null,
    avatarConfig: { colors },
  };

  function setColorAt(index: number, value: string) {
    setColors((prev) => prev.map((color, i) => (i === index ? value : color)));
  }

  async function persist(config: AvatarConfig | null, which: "save" | "reset") {
    setError(null);
    setPendingAction(which);
    try {
      await action.run(async () => {
        dispatch(setUser(await updateUser(user.id, { avatarConfig: config })));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save avatar");
    }
  }

  function handleSave() {
    void persist({ colors }, "save");
  }

  function handleReset() {
    setColors([...DEFAULT_AVATAR_PALETTE]);
    void persist(null, "reset");
  }

  return (
    <section className="flex flex-col gap-6 rounded-2xl glass-panel-strong p-6">
      <h2 className="font-display text-lg font-semibold tracking-tight text-on-surface">Avatar</h2>

      <AvatarField user={user} onChange={(updated) => dispatch(setUser(updated))} />

      <div className="flex flex-col gap-1 border-t border-glass-border pt-6">
        <h3 className="text-sm font-semibold text-on-surface">Generated avatar</h3>
        <p className="text-xs text-on-surface-variant">Used when no image is uploaded.</p>
      </div>

      <div className="flex items-center gap-4">
        <Avatar user={previewUser} size={96} />
      </div>

      <PalettePicker colors={colors} onChange={setColorAt} />

      <div className="flex flex-col items-end gap-2">
        {error && <p className="text-xs text-error">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={action.inFlight}
            status={pendingAction === "save" ? action.status : "idle"}
            pendingLabel="Saving…"
            doneLabel="Saved!"
          >
            Save
          </Button>
          <Button
            variant="ghost"
            onClick={handleReset}
            disabled={action.inFlight}
            status={pendingAction === "reset" ? action.status : "idle"}
            pendingLabel="Resetting…"
            doneLabel="Reset!"
          >
            Reset to default
          </Button>
        </div>
      </div>
    </section>
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
    <fieldset className="flex flex-col gap-2">
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
