/** @module i18n/load — Loads a language's catalog and Zod messages on demand, one chunk per language. */
import { z } from "zod";
import type { Locale } from "./config";
import { en, type Messages } from "./messages/en";

const CATALOGS: Record<Locale, () => Promise<Messages>> = {
  en: async () => en,
  ja: () => import("./messages/ja").then((m) => m.ja),
  es: () => import("./messages/es").then((m) => m.es),
  "zh-CN": () => import("./messages/zh-CN").then((m) => m.zhCN),
  ko: () => import("./messages/ko").then((m) => m.ko),
  fr: () => import("./messages/fr").then((m) => m.fr),
};

const ZOD_LOCALES: Record<Locale, () => Promise<{ default: () => Partial<z.core.$ZodConfig> }>> = {
  en: () => import("zod/v4/locales/en.js"),
  ja: () => import("zod/v4/locales/ja.js"),
  es: () => import("zod/v4/locales/es.js"),
  "zh-CN": () => import("zod/v4/locales/zh-CN.js"),
  ko: () => import("zod/v4/locales/ko.js"),
  fr: () => import("zod/v4/locales/fr.js"),
};

/**
 * Load a language's catalog.
 *
 * @param locale - The language.
 * @returns Its messages.
 */
export function loadMessages(locale: Locale): Promise<Messages> {
  return CATALOGS[locale]();
}

/**
 * Make Zod's built-in validation messages (the generated API schemas rely on
 * them) come out in a language. Zod's config is per process, so this is for the
 * browser only.
 *
 * @param locale - The language.
 */
export async function applyZodLocale(locale: Locale): Promise<void> {
  const { default: messages } = await ZOD_LOCALES[locale]();
  z.config(messages());
}
