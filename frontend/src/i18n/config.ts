/** @module i18n/config — The languages the GUI ships in, and how a browser's preference maps onto them. */
import type { User } from "@/lib/api";

/** A language the GUI is translated into; generated from the backend's `Language` literal. */
export type Locale = NonNullable<User["language"]>;

/** The language shown when nothing else decides, and the one every catalog falls back to. */
export const DEFAULT_LOCALE: Locale = "en";

/** Each language under its own name, so a reader can find theirs whatever the GUI is showing. */
export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  ja: "日本語",
  es: "Español",
  "zh-CN": "简体中文",
  ko: "한국어",
  fr: "Français",
};

/** Every language the GUI is translated into. */
export const LOCALES = Object.keys(LOCALE_NAMES) as Locale[];

/** Cookie remembering the language between requests, so the server can render in it. */
export const LOCALE_COOKIE = "a2flow.locale";

/**
 * Narrow an untrusted value (a cookie, an API field) to a supported language.
 *
 * @param value - The value to check.
 * @returns Whether it names a supported language.
 */
export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && Object.hasOwn(LOCALE_NAMES, value);
}

/** Map one BCP 47 tag to a supported language, or `null` when none fits. */
function matchTag(tag: string): Locale | null {
  let parsed: Intl.Locale;
  try {
    parsed = new Intl.Locale(tag);
  } catch {
    return null;
  }
  if (parsed.language === "zh") {
    // Only Simplified ships: a Traditional reader moves on to their next
    // preference rather than being handed the other script.
    const isTraditional =
      parsed.script === "Hant" ||
      (!parsed.script && ["TW", "HK", "MO"].includes(parsed.region ?? ""));
    return isTraditional ? null : "zh-CN";
  }
  return isLocale(parsed.language) ? parsed.language : null;
}

/**
 * Pick the first supported language from a preference list.
 *
 * @param tags - BCP 47 tags, most preferred first (e.g. `navigator.languages`).
 * @returns The first that maps onto a supported language, else {@link DEFAULT_LOCALE}.
 */
export function matchLocale(tags: readonly string[]): Locale {
  for (const tag of tags) {
    const match = matchTag(tag);
    if (match) return match;
  }
  return DEFAULT_LOCALE;
}

/**
 * Read an `Accept-Language` header into a preference list.
 *
 * @param header - The raw header value, if the request carried one.
 * @returns The tags ordered by descending `q`, stable among equals.
 */
export function parseAcceptLanguage(header: string | null | undefined): string[] {
  if (!header) return [];
  return header
    .split(",")
    .map((part) => {
      const [tag, ...params] = part.trim().split(";");
      const q = params.map((p) => p.trim()).find((p) => p.startsWith("q="));
      return { tag: tag.trim(), q: q ? Number(q.slice(2)) : 1 };
    })
    .filter(({ tag, q }) => tag && tag !== "*" && q > 0)
    .sort((a, b) => b.q - a.q)
    .map(({ tag }) => tag);
}
