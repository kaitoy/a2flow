/** @module ProfileHero — Identity banner of the profile page: who you are, and the way in to editing your avatar. */
"use client";

import { Camera, Check, TriangleAlert } from "lucide-react";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { useT } from "@/i18n/provider";
import { formatUserName, type User } from "@/lib/api";
import { roleLabel } from "@/lib/roles";

/** Diameter, in pixels, of the hero avatar inside its glass frame. */
const AVATAR_SIZE = 120;

/** Props for {@link ProfileHero}. */
export interface ProfileHeroProps {
  /** The signed-in user the hero introduces. */
  user: User;
  /** Called when the avatar is activated, to open the avatar editor. */
  onEditAvatar: () => void;
}

/**
 * The profile page's identity card: an accent-washed banner, the user's avatar sitting
 * across its lower edge, and the name, handle, roles, and account status beside
 * it.
 *
 * This carries the page's `h1`, and the heading is the **user's own name**
 * rather than the word "Profile" — the same rule DESIGN.md sets for admin detail
 * pages, which title themselves with the record they show. "Profile" survives as
 * a `text-label` eyebrow above it, so the page still says what it is
 * without spending the largest type on a word every visitor already knows.
 *
 * The avatar is the editor's only trigger: it is a real button that opens the
 * avatar dialog, carrying a standing camera badge and darkening under a full
 * camera scrim on hover and keyboard focus.
 *
 * `enabled` and `emailVerified` render here as status pills rather than as
 * `DetailItem` rows: they are the two attributes a user actually needs to notice
 * about their own account, and "Enabled: Yes" buries that under a label.
 */
export function ProfileHero({ user, onEditAvatar }: ProfileHeroProps) {
  const t = useT();
  const displayName = formatUserName(user) || user.username;
  const roles = user.roles ?? [];

  return (
    <section className="relative overflow-hidden rounded-2xl glass-panel-strong">
      {/* A wash of the accent, fading out to the right and masked away
          downward so the band ends in
          light rather than in a hard rule. A hairline edge here would land
          across the name (the text block is taller than any banner that still
          reads as a banner) and be mistaken for an underline. */}
      <span
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-32 bg-gradient-to-r from-accent/25 to-transparent mask-b-from-30%"
      />

      <div className="relative flex flex-col items-center gap-4 px-6 pt-14 pb-6 text-center sm:flex-row sm:items-end sm:gap-6 sm:text-left">
        <Tooltip label={t("profile.editAvatar")}>
          <button
            type="button"
            onClick={onEditAvatar}
            aria-label={t("profile.editAvatar")}
            className={[
              "group relative shrink-0 rounded-full glass-panel-strong p-1",
              "transition-[box-shadow] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)]",
              "hover:shadow-glow",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
            ].join(" ")}
          >
            <Avatar user={user} size={AVATAR_SIZE} />
            {/* Revealed only on hover and keyboard focus: a permanent full-cover
                scrim would hide the very thing it offers to edit. */}
            <span
              aria-hidden="true"
              className={[
                "absolute inset-1 flex items-center justify-center rounded-full bg-black/45 text-white",
                "opacity-0 transition-opacity duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)]",
                "group-hover:opacity-100 group-focus-visible:opacity-100",
              ].join(" ")}
            >
              <Camera size={28} strokeWidth={1.8} />
            </span>
            {/* The standing affordance. It is always visible rather than
                hover-revealed because hover is not a gesture a touchscreen has —
                and `pointer-coarse:` is no help here either: Chrome reports
                coarse on hybrid touchscreen laptops, which would pin the scrim
                open for mouse users too. A badge reads as "editable" at every
                size without covering the avatar. */}
            <span
              aria-hidden="true"
              className="absolute right-1 bottom-1 flex h-8 w-8 items-center justify-center rounded-full glass-panel-strong text-accent"
            >
              <Camera size={16} strokeWidth={1.8} />
            </span>
          </button>
        </Tooltip>

        <div className="flex min-w-0 flex-col items-center gap-1.5 sm:items-start sm:pb-1">
          <span className="text-label">{t("common.profile")}</span>
          <h1 className="min-w-0 max-w-full truncate font-display text-3xl font-semibold tracking-tight text-on-surface">
            {displayName}
          </h1>
          <span className="min-w-0 max-w-full truncate font-mono text-sm text-on-surface-variant">
            @{user.username}
          </span>

          {roles.length > 0 && (
            <div className="mt-1 flex flex-wrap justify-center gap-1.5 sm:justify-start">
              {roles.map((role) => (
                <Badge key={role}>{roleLabel(role)}</Badge>
              ))}
            </div>
          )}

          <div className="mt-1 flex flex-wrap justify-center gap-2 sm:justify-start">
            <StatusPill
              ok={user.enabled}
              okLabel={t("common.enabled")}
              ngLabel={t("users.disabled")}
            />
            <StatusPill
              ok={user.emailVerified}
              okLabel={t("users.emailVerified")}
              ngLabel={t("profile.emailNotVerified")}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

/** Props for {@link StatusPill}. */
interface StatusPillProps {
  /** Whether the flag is in its healthy state. */
  ok: boolean;
  /** Label shown when {@link StatusPillProps.ok} is true. */
  okLabel: string;
  /** Label shown when {@link StatusPillProps.ok} is false. */
  ngLabel: string;
}

/**
 * A boolean account flag drawn as a tinted pill instead of a label/value pair.
 *
 * The state is marked twice over — by the tint and by the glyph — so it survives
 * being read in grayscale or at a glance. `success` and `alert` are the semantic
 * tokens DESIGN.md reserves for exactly this, and the tint stays well below the
 * accent's strength so a healthy profile does not light up like a warning.
 */
function StatusPill({ ok, okLabel, ngLabel }: StatusPillProps) {
  const tint = ok
    ? "border-success/30 bg-success/12 text-success"
    : "border-alert/30 bg-alert/12 text-alert";
  const Icon = ok ? Check : TriangleAlert;

  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-medium ${tint}`}
    >
      <Icon size={14} strokeWidth={2} aria-hidden="true" />
      {ok ? okLabel : ngLabel}
    </span>
  );
}
