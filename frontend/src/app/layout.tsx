/** @module RootLayout — Applies fonts, theme flash-prevention script, and global providers. */
import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { ThemeProvider } from "@/components/ThemeProvider";
import { Toaster } from "@/components/ui/toast";
import { StoreProvider } from "@/store/provider";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "A2Flow",
  description: "AI chat powered by Google ADK",
};

const NO_FLASH_SCRIPT = `(() => {
  try {
    const stored = localStorage.getItem('a2flow.theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = stored === 'light' || stored === 'dark' ? stored : prefersDark ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
  } catch (_) {
    document.documentElement.dataset.theme = 'light';
  }
})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={spaceGrotesk.variable}>
      <head>
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: trusted inline script for FOUC prevention */}
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_SCRIPT }} />
      </head>
      <body className={inter.className}>
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
