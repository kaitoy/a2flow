/**
 * @module i18n/translate — Turns a catalog into a translator: placeholders, plurals,
 * and embedded React nodes. Has no React state of its own.
 */
import { createElement, Fragment, type ReactNode } from "react";
import type { Locale } from "./config";
import { DEFAULT_LOCALE } from "./config";
import { en, type MessageKey, type Messages } from "./messages/en";

/** Values substituted for `{name}` placeholders. */
export type MessageParams = Record<string, string | number>;

/** Translates catalog keys into one language. */
export interface Translator {
  /**
   * Translate a key. A plural message picks its form from `params.count`.
   *
   * @param key - The catalog key.
   * @param params - Values for the message's placeholders.
   */
  (key: MessageKey, params?: MessageParams): string;
  /**
   * Translate a string that may not be a key at all, returning it unchanged when
   * it isn't: for values that are a key on one path and ready-made text on
   * another, such as a form error from either a schema or a Zod locale.
   *
   * @param text - A catalog key or finished text.
   * @param params - Values for the message's placeholders.
   */
  maybe(text: string, params?: MessageParams): string;
  /**
   * Translate a key whose placeholders hold React nodes (a link, a `<code>`).
   *
   * @param key - The catalog key.
   * @param nodes - Node for each placeholder.
   */
  rich(key: MessageKey, nodes: Record<string, ReactNode>): ReactNode;
  /** The language this translator produces. */
  locale: Locale;
}

const PLACEHOLDER = /\{(\w+)\}/g;

/**
 * Build a translator over a catalog, falling back to English for any key it
 * lacks (the type system rules that out at build time; a stale lazy-loaded chunk
 * can still get there at runtime).
 *
 * @param locale - The language `messages` is in.
 * @param messages - The catalog.
 * @returns The translator.
 */
export function createTranslator(locale: Locale, messages: Messages): Translator {
  const plural = new Intl.PluralRules(locale);

  function template(key: string, count: unknown): string | undefined {
    const message = messages[key as MessageKey] ?? en[key as MessageKey];
    if (message === undefined || typeof message === "string") return message;
    const form = typeof count === "number" ? plural.select(count) : "other";
    return message[form] ?? message.other;
  }

  function fill(text: string, params?: MessageParams): string {
    if (!params) return text;
    return text.replace(PLACEHOLDER, (slot, name: string) =>
      params[name] === undefined ? slot : String(params[name])
    );
  }

  const t = ((key: MessageKey, params?: MessageParams) =>
    fill(template(key, params?.count) ?? key, params)) as Translator;

  t.maybe = (text, params) => {
    const found = template(text, params?.count);
    return found === undefined ? text : fill(found, params);
  };

  t.rich = (key, nodes) => {
    // split() with a capture group alternates literal text and placeholder names.
    const parts = (template(key, nodes.count) ?? key).split(PLACEHOLDER);
    return createElement(
      Fragment,
      null,
      ...parts.map((part, i) => (i % 2 === 1 ? (nodes[part] ?? `{${part}}`) : part))
    );
  };

  t.locale = locale;
  return t;
}

/**
 * A backend status value as a reader sees it: its translation under `status.`, or
 * the value itself with underscores as spaces if it has none.
 *
 * @param status - The value, e.g. `in_progress`.
 * @param t - The translator to use.
 * @returns The text to show.
 */
export function translateStatus(status: string, t: Translator): string {
  const key = `status.${status}`;
  const text = t.maybe(key);
  return text === key ? status.replaceAll("_", " ") : text;
}

/** The translator for the default language. */
export const defaultTranslator = createTranslator(DEFAULT_LOCALE, en);

let activeTranslator = defaultTranslator;

/**
 * The translator for code outside React (`lib/api.ts`, text put into the store).
 * Components and hooks use `useT` instead: this holds one value per process, so
 * it only ever leaves the default language in the browser.
 *
 * @returns The translator for the language currently on screen.
 */
export function getActiveTranslator(): Translator {
  return activeTranslator;
}

/**
 * Point {@link getActiveTranslator} at another language. Does nothing on the
 * server, where one module instance serves every request and a value set for one
 * would leak into the next.
 *
 * @param translator - The translator now on screen.
 */
export function setActiveTranslator(translator: Translator): void {
  if (typeof window !== "undefined") activeTranslator = translator;
}
