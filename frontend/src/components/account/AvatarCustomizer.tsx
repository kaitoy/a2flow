/** @module AvatarCustomizer — Self-service editor for a user's generated avatar. */
"use client";

import { humation1 } from "@humation/assets-humation-1";
import type { ColorSlot, PartOption, UiGroup } from "@humation/core";
import { createPartPreview, getPartsForUiGroup } from "@humation/core";
import { useMemo, useState } from "react";
import { Avatar, type AvatarUser } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { type AvatarConfig, updateUser } from "@/lib/api";
import { setUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";

/** Props for {@link AvatarCustomizer}. */
interface AvatarCustomizerProps {
  /** The signed-in user whose generated avatar is being customized. */
  user: AvatarUser;
}

/** How the avatar background is chosen. */
type BackgroundMode = "default" | "transparent" | "color";

/** Fallback solid color shown in the background picker before one is chosen. */
const DEFAULT_BACKGROUND_COLOR = "#e2e8f0";

/**
 * UI groups sorted by their declared display order. The "bottom" group is
 * excluded: the Humation crop clips the lower-body layer, so its controls have
 * no visible effect on the rendered avatar.
 */
const SORTED_GROUPS: UiGroup[] = humation1.uiGroups
  .filter((group) => group.id !== "bottom")
  .sort((a, b) => a.order - b.order);

/**
 * Derive the initial {@link BackgroundMode} and color value from a stored config.
 *
 * @param background - The persisted background value, if any.
 * @returns The matching mode and a usable color value for the picker.
 */
function initBackground(background: string | null | undefined): {
  mode: BackgroundMode;
  color: string;
} {
  if (!background) return { mode: "default", color: DEFAULT_BACKGROUND_COLOR };
  if (background === "transparent") return { mode: "transparent", color: DEFAULT_BACKGROUND_COLOR };
  return { mode: "color", color: background };
}

/**
 * Editor that lets a signed-in user customize their generated (Humation) avatar:
 * pick a part per group, override colors, and choose a background. Selections and
 * colors are stored as an {@link AvatarConfig} on the user; saving refreshes the
 * auth slice so every avatar across the app updates immediately.
 */
export function AvatarCustomizer({ user }: AvatarCustomizerProps) {
  const dispatch = useAppDispatch();
  const initial = user.avatarConfig ?? null;

  const [selections, setSelections] = useState<Record<string, string>>(() => ({
    ...(initial?.selections ?? {}),
  }));
  const [colors, setColors] = useState<Record<string, string>>(() => ({
    ...(initial?.colors ?? {}),
  }));
  const initialBg = initBackground(initial?.background);
  const [bgMode, setBgMode] = useState<BackgroundMode>(initialBg.mode);
  const [bgColor, setBgColor] = useState<string>(initialBg.color);

  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The background value the renderer and persisted config should use.
  const background = bgMode === "transparent" ? "transparent" : bgMode === "color" ? bgColor : null;

  // The live preview mirrors the real Avatar render with the in-progress config.
  const previewUser: AvatarUser = {
    ...user,
    avatarUpdatedAt: null,
    avatarConfig: { selections, colors, background },
  };

  function selectPart(part: PartOption) {
    setSelections((prev) => ({ ...prev, [part.selectionSlot]: part.id }));
  }

  function clearSlot(slotId: string) {
    setSelections((prev) => {
      const next = { ...prev };
      delete next[slotId];
      return next;
    });
  }

  function setColor(slotId: string, value: string) {
    setColors((prev) => ({ ...prev, [slotId]: value }));
  }

  async function persist(config: AvatarConfig | null) {
    setPending(true);
    setError(null);
    try {
      dispatch(setUser(await updateUser(user.id, { avatarConfig: config })));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save avatar");
    } finally {
      setPending(false);
    }
  }

  function handleSave() {
    const config: AvatarConfig = { selections, colors };
    if (background !== null) config.background = background;
    void persist(config);
  }

  function handleReset() {
    setSelections({});
    setColors({});
    setBgMode("default");
    setBgColor(DEFAULT_BACKGROUND_COLOR);
    void persist(null);
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-8">
      <h1 className="text-3xl font-semibold tracking-tight text-gradient-accent">
        Customize Avatar
      </h1>

      <div className="flex flex-col gap-6 rounded-2xl glass-panel-strong p-6">
        <div className="flex items-center gap-4">
          <Avatar user={previewUser} size={96} />
        </div>

        {SORTED_GROUPS.map((group) => (
          <PartGroup
            key={group.id}
            group={group}
            colors={colors}
            selections={selections}
            onSelect={selectPart}
            onClear={clearSlot}
          />
        ))}

        <ColorPickers colors={colors} onChange={setColor} />

        <BackgroundPicker
          mode={bgMode}
          color={bgColor}
          onModeChange={setBgMode}
          onColorChange={setBgColor}
        />

        <div className="flex flex-col items-end gap-2">
          {error && <p className="text-xs text-error">{error}</p>}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="primary" onClick={handleSave} disabled={pending}>
              {pending ? "Saving…" : "Save"}
            </Button>
            <Button variant="ghost" onClick={handleReset} disabled={pending}>
              Reset to default
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Props for {@link PartGroup}. */
interface PartGroupProps {
  /** The UI group whose parts are shown. */
  group: UiGroup;
  /** Current color overrides, used to render the thumbnails. */
  colors: Record<string, string>;
  /** Current part selections per slot. */
  selections: Record<string, string>;
  /** Called when a part thumbnail is chosen. */
  onSelect: (part: PartOption) => void;
  /** Called to clear the selections for the group's slots (revert to seeded). */
  onClear: (slotId: string) => void;
}

/** A labeled row of selectable part thumbnails for one UI group. */
function PartGroup({ group, colors, selections, onSelect, onClear }: PartGroupProps) {
  // Memoize per group + colors so thumbnails only regenerate when colors change.
  const parts = useMemo(() => getPartsForUiGroup(humation1, group.id), [group.id]);
  const previews = useMemo(
    () => parts.map((part) => createPartPreview(humation1, part, { colors }).toDataUri()),
    [parts, colors]
  );

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[11px] font-bold uppercase tracking-[0.08em] text-on-surface-variant">
        {group.label}
      </legend>
      <div className="flex flex-wrap gap-2">
        {group.selectionSlots.map((slotId) => (
          <button
            key={`clear-${slotId}`}
            type="button"
            onClick={() => onClear(slotId)}
            className="flex h-16 w-16 items-center justify-center rounded-xl border border-glass-border bg-glass text-[11px] text-on-surface-variant transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          >
            Default
          </button>
        ))}
        {parts.map((part, i) => {
          const active = selections[part.selectionSlot] === part.id;
          return (
            <button
              key={part.id}
              type="button"
              onClick={() => onSelect(part)}
              aria-pressed={active}
              title={part.name ?? part.id}
              className={[
                "h-16 w-16 overflow-hidden rounded-xl border transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
                active ? "border-accent shadow-glow" : "border-glass-border hover:border-accent/60",
              ].join(" ")}
            >
              {/* biome-ignore lint/performance/noImgElement: a generated in-memory data-URI thumbnail; next/image cannot optimize it. */}
              <img
                src={previews[i]}
                alt={part.name ?? part.id}
                className="h-full w-full object-cover"
              />
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Props for {@link ColorPickers}. */
interface ColorPickersProps {
  /** Current color overrides per color slot. */
  colors: Record<string, string>;
  /** Called when a color slot value changes. */
  onChange: (slotId: string, value: string) => void;
}

/** A grid of color inputs, one per Humation color slot. */
function ColorPickers({ colors, onChange }: ColorPickersProps) {
  // Exclude the "bottom" color: it tints the clipped lower-body layer, which is
  // not visible in the rendered avatar.
  const slots: ColorSlot[] = humation1.colors.filter((slot) => slot.id !== "bottom");
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[11px] font-bold uppercase tracking-[0.08em] text-on-surface-variant">
        Colors
      </legend>
      <div className="flex flex-wrap gap-4">
        {slots.map((slot) => (
          <label key={slot.id} className="flex items-center gap-2 text-sm text-on-surface">
            <input
              type="color"
              value={colors[slot.id] ?? slot.default}
              onChange={(e) => onChange(slot.id, e.target.value)}
              className="h-8 w-8 cursor-pointer rounded-md border border-glass-border bg-transparent"
            />
            {slot.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Props for {@link BackgroundPicker}. */
interface BackgroundPickerProps {
  /** The current background mode. */
  mode: BackgroundMode;
  /** The current custom background color. */
  color: string;
  /** Called when the background mode changes. */
  onModeChange: (mode: BackgroundMode) => void;
  /** Called when the custom background color changes. */
  onColorChange: (color: string) => void;
}

/** Background chooser: default, transparent, or a custom solid color. */
function BackgroundPicker({ mode, color, onModeChange, onColorChange }: BackgroundPickerProps) {
  const modes: { value: BackgroundMode; label: string }[] = [
    { value: "default", label: "Default" },
    { value: "transparent", label: "Transparent" },
    { value: "color", label: "Custom" },
  ];
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[11px] font-bold uppercase tracking-[0.08em] text-on-surface-variant">
        Background
      </legend>
      <div className="flex flex-wrap items-center gap-4">
        {modes.map((m) => (
          <label key={m.value} className="flex items-center gap-1.5 text-sm text-on-surface">
            <input
              type="radio"
              name="background-mode"
              value={m.value}
              checked={mode === m.value}
              onChange={() => onModeChange(m.value)}
              className="cursor-pointer accent-accent"
            />
            {m.label}
          </label>
        ))}
        {mode === "color" && (
          <input
            type="color"
            value={color}
            onChange={(e) => onColorChange(e.target.value)}
            aria-label="Background color"
            className="h-8 w-8 cursor-pointer rounded-md border border-glass-border bg-transparent"
          />
        )}
      </div>
    </fieldset>
  );
}
