"use client";

import { AlertTriangle } from "lucide-react";
import { Archivo, Geist_Mono, Inter } from "next/font/google";
import Script from "next/script";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { DEFAULT_LOCALE, isLocale, LOCALE_COOKIE, type Locale, matchLocale } from "@/i18n/config";
import { NO_FLASH_THEME_SCRIPT } from "@/lib/no-flash-theme-script";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });
// Variable on both axes: headings are set wider than the default width.
const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
  axes: ["wdth"],
});
const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
});

/**
 * This page's own text. The root layout that loads the catalog is what crashed,
 * and fetching a chunk is one more thing that could fail here, so the few strings
 * a last-resort page needs travel with it.
 */
const TEXT: Record<Locale, { title: string; description: string; retry: string }> = {
  en: {
    title: "Something went wrong",
    description: "An unexpected error occurred.",
    retry: "Try again",
  },
  ja: {
    title: "問題が発生しました",
    description: "予期しないエラーが発生しました。",
    retry: "再試行",
  },
  es: {
    title: "Se produjo un error",
    description: "Ocurrió un error inesperado.",
    retry: "Reintentar",
  },
  "zh-CN": {
    title: "出现问题",
    description: "发生了意外错误。",
    retry: "重试",
  },
  ko: {
    title: "문제가 발생했습니다",
    description: "예기치 않은 오류가 발생했습니다.",
    retry: "다시 시도",
  },
  fr: {
    title: "Une erreur est survenue",
    description: "Une erreur inattendue s'est produite.",
    retry: "Réessayer",
  },
};

/** The remembered language if the cookie holds one, else the browser's. */
function browserLocale(): Locale {
  const prefix = `${LOCALE_COOKIE}=`;
  const remembered = document.cookie
    .split("; ")
    .find((row) => row.startsWith(prefix))
    ?.slice(prefix.length);
  return isLocale(remembered) ? remembered : matchLocale(navigator.languages);
}

/**
 * Fallback content shown when the root layout itself throws. Exported
 * separately from the `<html>`/`<body>` wrapper below so it can be
 * unit-tested without nesting a document inside the test DOM's own document.
 */
export function GlobalErrorContent({ reset }: { reset: () => void }) {
  const [locale, setLocale] = useState(DEFAULT_LOCALE);
  useEffect(() => {
    const resolved = browserLocale();
    document.documentElement.lang = resolved;
    setLocale(resolved);
  }, []);
  const text = TEXT[locale];
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4">
      <EmptyState
        icon={AlertTriangle}
        animation="wiggle"
        title={text.title}
        description={text.description}
      />
      <Button variant="secondary" onClick={reset}>
        {text.retry}
      </Button>
    </div>
  );
}

/**
 * Last-resort error boundary for a crash in the root layout itself. Fully
 * replaces the app tree, so it declares its own `<html>`/`<body>` and
 * re-establishes fonts, the no-flash theme script, and global styles.
 * Deliberately omits `ThemeProvider`/`I18nProvider`/`StoreProvider`/`Toaster` —
 * the theme script sets a plain CSS attribute the stylesheet reads directly,
 * `EmptyState`/`Button` have no Redux dependency, and the content carries its own
 * text, so none of those providers are required here.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("uncaught root layout error", error);
  }, [error]);

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${archivo.variable} ${geistMono.variable}`}
    >
      <body className={inter.className}>
        <Script
          id="no-flash-theme"
          strategy="beforeInteractive"
          // biome-ignore lint/security/noDangerouslySetInnerHtml: trusted inline script for FOUC prevention
          dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }}
        />
        <GlobalErrorContent reset={reset} />
      </body>
    </html>
  );
}
