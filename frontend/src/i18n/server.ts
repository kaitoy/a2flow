/** @module i18n/server — Resolves the language of a request, for the root layout and server components. */
import { cookies, headers } from "next/headers";
import { isLocale, LOCALE_COOKIE, type Locale, matchLocale, parseAcceptLanguage } from "./config";
import { loadMessages } from "./load";
import { createTranslator, type Translator } from "./translate";

/**
 * Decide the language of the current request: the remembered one if the cookie
 * holds a supported value, else the best match for `Accept-Language`, else English.
 *
 * @returns The language to render in.
 */
export async function resolveLocale(): Promise<Locale> {
  const remembered = (await cookies()).get(LOCALE_COOKIE)?.value;
  if (isLocale(remembered)) return remembered;
  return matchLocale(parseAcceptLanguage((await headers()).get("accept-language")));
}

/**
 * The translator for a server component.
 *
 * @returns A translator for the current request's language.
 */
export async function getServerT(): Promise<Translator> {
  const locale = await resolveLocale();
  return createTranslator(locale, await loadMessages(locale));
}
