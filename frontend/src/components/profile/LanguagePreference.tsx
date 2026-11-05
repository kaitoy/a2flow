/** @module LanguagePreference — The profile card where a user picks the language the GUI is shown in. */
"use client";

import { Languages } from "lucide-react";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import { SectionCard } from "@/components/ui/section-card";
import { Select } from "@/components/ui/select";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { LOCALE_NAMES, LOCALES, type Locale } from "@/i18n/config";
import { useT } from "@/i18n/provider";
import { type User, updateUser } from "@/lib/api";
import { setUser } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/** Option value standing for "no language set"; `Select` needs a string. */
const FOLLOW_BROWSER = "";

/**
 * Lets the signed-in user choose their GUI language, or leave it to the browser.
 *
 * Saving only updates the user in the store; {@link import("@/i18n/locale-sync").LocaleSync}
 * sees the change and switches the screen. Disabled while impersonating: the page
 * shows the target's record, but the screen stays in the impersonator's language.
 *
 * @param props.user - The user whose setting is edited.
 */
export function LanguagePreference({ user }: { user: User }) {
  const t = useT();
  const dispatch = useAppDispatch();
  const impersonating = useAppSelector((s) => s.auth.impersonatedBy !== null);
  const action = useAsyncAction({ showDone: false });

  async function handleChange(value: string) {
    const language = value === FOLLOW_BROWSER ? null : (value as Locale);
    // A failure is toasted by api.ts, and the select keeps showing the stored value.
    await action
      .run(async () => {
        dispatch(setUser(await updateUser(user.id, { language })));
      })
      .catch(() => {});
  }

  return (
    <SectionCard icon={Languages} title={t("profile.preferences")}>
      <DetailList singleColumn>
        <DetailItem
          label={t("profile.language.label")}
          value={
            <>
              <Select
                aria-label={t("profile.language.label")}
                className="max-w-xs"
                disabled={impersonating || action.inFlight}
                value={user.language ?? FOLLOW_BROWSER}
                onChange={handleChange}
                options={[
                  { value: FOLLOW_BROWSER, label: t("profile.language.browser") },
                  ...LOCALES.map((locale) => ({ value: locale, label: LOCALE_NAMES[locale] })),
                ]}
              />
              {impersonating && (
                <p className="mt-1.5 text-xs text-on-surface-variant">
                  {t("profile.language.impersonating")}
                </p>
              )}
            </>
          }
        />
      </DetailList>
    </SectionCard>
  );
}
