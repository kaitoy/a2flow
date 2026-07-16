/** @module RootLayout — Applies fonts, theme flash-prevention script, and global providers. */
import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import Script from "next/script";
import { ThemeProvider } from "@/components/ThemeProvider";
import { Toaster } from "@/components/ui/toast";
import { NO_FLASH_THEME_SCRIPT } from "@/lib/no-flash-theme-script";
import { StoreProvider } from "@/store/provider";
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

export const metadata: Metadata = {
  title: "A2Flow",
  description: "AI chat powered by Google ADK",
};

/**
 * Viewport configuration. `viewportFit: "cover"` lets the app paint behind
 * notches/home indicators so `env(safe-area-inset-*)` paddings (e.g. on the
 * chat input) take effect on devices with them.
 */
export const viewport: Viewport = {
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
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
        <ThemeProvider>
          <StoreProvider>
            <Toaster />
            {children}
          </StoreProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
