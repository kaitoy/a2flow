/** @module i18n/locale-sync — Makes the screen follow the signed-in user's language setting. */
"use client";

import { useEffect } from "react";
import { useAppSelector } from "@/store/hooks";
import { LOCALE_COOKIE, type Locale, matchLocale } from "./config";
import { useSetLocale, useT } from "./provider";

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

/** Remember an explicit choice for the next request, or forget it so the browser decides. */
function writeLocaleCookie(locale: Locale | null): void {
  // biome-ignore lint/suspicious/noDocumentCookie: the Cookie Store API is not available in every supported browser
  document.cookie = locale
    ? `${LOCALE_COOKIE}=${locale}; path=/; max-age=${ONE_YEAR_SECONDS}; samesite=lax`
    : `${LOCALE_COOKIE}=; path=/; max-age=0; samesite=lax`;
}

/**
 * Apply the real user's language setting once it is known, and on every change:
 * set language wins, else the browser's. While impersonating, that is still the
 * impersonator's, who has to be able to read the screen. Nothing happens signed
 * out, so the login page stays in the last language used.
 *
 * Renders nothing; lives under the store, which the provider above it cannot read.
 */
export function LocaleSync() {
  const actor = useAppSelector((s) => s.auth.impersonatedBy ?? s.auth.user);
  const signedIn = actor !== null;
  const language = actor?.language ?? null;
  const setLocale = useSetLocale();
  const { locale } = useT();

  useEffect(() => {
    if (!signedIn) return;
    writeLocaleCookie(language);
    const target = language ?? matchLocale(navigator.languages);
    if (target !== locale) void setLocale(target);
  }, [signedIn, language, locale, setLocale]);

  return null;
}
