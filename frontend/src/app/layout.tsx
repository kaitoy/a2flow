/** @module RootLayout — Applies fonts, the request's language, theme flash-prevention script, and global providers. */
import type { Metadata, Viewport } from "next";
import { Archivo, Geist_Mono, Inter } from "next/font/google";
import Script from "next/script";
import { ThemeProvider } from "@/components/ThemeProvider";
import { Toaster } from "@/components/ui/toast";
import { DEFAULT_LOCALE } from "@/i18n/config";
import { loadMessages } from "@/i18n/load";
import { LocaleSync } from "@/i18n/locale-sync";
import { I18nProvider } from "@/i18n/provider";
import { getServerT, resolveLocale } from "@/i18n/server";
import { NO_FLASH_THEME_SCRIPT } from "@/lib/no-flash-theme-script";
import { StoreProvider } from "@/store/provider";
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

/** Page metadata, with the description in the request's language. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getServerT();
  return { title: "A2Flow", description: t("app.description") };
}

/**
 * Viewport configuration. `viewportFit: "cover"` lets the app paint behind
 * notches/home indicators so `env(safe-area-inset-*)` paddings (e.g. on the
 * chat input) take effect on devices with them.
 */
export const viewport: Viewport = {
  viewportFit: "cover",
};

/**
 * The document shell. Reading the language from the request makes every route
 * render dynamically, which costs little: pages fetch their data on the client.
 */
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await resolveLocale();
  const messages = locale === DEFAULT_LOCALE ? undefined : await loadMessages(locale);
  return (
    <html
      lang={locale}
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
        <ThemeProvider>
          <I18nProvider locale={locale} messages={messages}>
            <StoreProvider>
              <LocaleSync />
              <Toaster />
              {children}
            </StoreProvider>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
