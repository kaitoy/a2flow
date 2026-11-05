/** @module i18n/provider — Holds the language on screen and hands its translator to components. */
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { DEFAULT_LOCALE, type Locale } from "./config";
import { applyZodLocale, loadMessages } from "./load";
import type { Messages } from "./messages/en";
import {
  createTranslator,
  defaultTranslator,
  setActiveTranslator,
  type Translator,
} from "./translate";

interface I18nContextValue {
  t: Translator;
  setLocale: (locale: Locale) => Promise<void>;
}

/**
 * English until an {@link I18nProvider} says otherwise, so a component rendered
 * without one (a unit test, the error page outside the root layout) still works.
 */
const I18nContext = createContext<I18nContextValue>({
  t: defaultTranslator,
  setLocale: async () => {},
});

/** Props for {@link I18nProvider}. */
export interface I18nProviderProps {
  /** The language the server rendered in. */
  locale: Locale;
  /** Its catalog; omit for English, which is always bundled. */
  messages?: Messages;
  children: React.ReactNode;
}

/**
 * Provide the language resolved by the server to the tree, and let it change
 * without a reload.
 */
export function I18nProvider({ locale, messages, children }: I18nProviderProps) {
  const [t, setT] = useState(() => {
    const initial = messages ? createTranslator(locale, messages) : defaultTranslator;
    // During render, not in an effect: a child's effect runs before its parent's
    // and may already raise a toast.
    setActiveTranslator(initial);
    return initial;
  });
  const latestRequest = useRef(0);

  useEffect(() => {
    // English is what Zod starts in, so only another language needs loading.
    if (locale !== DEFAULT_LOCALE) void applyZodLocale(locale);
  }, [locale]);

  const setLocale = useCallback(async (next: Locale) => {
    const request = ++latestRequest.current;
    const [catalog] = await Promise.all([loadMessages(next), applyZodLocale(next)]);
    if (request !== latestRequest.current) return;
    const translator = createTranslator(next, catalog);
    setActiveTranslator(translator);
    document.documentElement.lang = next;
    setT(() => translator);
  }, []);

  const value = useMemo(() => ({ t, setLocale }), [t, setLocale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/**
 * The translator for the language on screen.
 *
 * @returns The translator; its `locale` names the language, for `Intl` and `toLocale*` calls.
 */
export function useT(): Translator {
  return useContext(I18nContext).t;
}

/**
 * Switch the language on screen.
 *
 * @returns A function loading a language and re-rendering the tree in it.
 */
export function useSetLocale(): (locale: Locale) => Promise<void> {
  return useContext(I18nContext).setLocale;
}
