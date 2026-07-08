"use client";

import { AlertTriangle } from "lucide-react";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import Script from "next/script";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import logger from "@/lib/logger";
import { NO_FLASH_THEME_SCRIPT } from "@/lib/no-flash-theme-script";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  weight: ["400", "500", "600", "700"],
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  weight: ["400", "700"],
});

/**
 * Fallback content shown when the root layout itself throws. Exported
 * separately from the `<html>`/`<body>` wrapper below so it can be
 * unit-tested without nesting a document inside jsdom's own document.
 */
export function GlobalErrorContent({ reset }: { reset: () => void }) {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4">
      <EmptyState
        icon={AlertTriangle}
        animation="wiggle"
        title="Something went wrong"
        description="An unexpected error occurred."
      />
      <Button variant="secondary" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}

/**
 * Last-resort error boundary for a crash in the root layout itself. Fully
 * replaces the app tree, so it declares its own `<html>`/`<body>` and
 * re-establishes fonts, the no-flash theme script, and global styles.
 * Deliberately omits `ThemeProvider`/`StoreProvider`/`Toaster` — the theme
 * script sets a plain CSS attribute the stylesheet reads directly, and
 * `EmptyState`/`Button` have no Redux dependency, so none of those providers
 * are required here.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    logger.error(error, "uncaught root layout error");
  }, [error]);

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${spaceGrotesk.variable} ${jetbrainsMono.variable}`}
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
