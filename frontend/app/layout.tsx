import type { Metadata } from "next";
import { DM_Sans, Newsreader } from "next/font/google";
import DesktopUpdater from "@/components/DesktopUpdater";
import "./globals.css";
import "./advocate.css";
const uiFont = DM_Sans({ subsets: ["latin"], variable: "--font-ui", display: "swap" });
const editorialFont = Newsreader({ subsets: ["latin"], variable: "--font-editorial", display: "swap", adjustFontFallback: false });

export const metadata: Metadata = {
  title: {
    default: "Corpusil",
    template: "%s | Corpusil",
  },
  description: "Evidence-led legal research and decision support for India.",
  icons: {
    // The square mark, not the wordmark. corpusil-logo.png is 1774x887 and
    // 1.3 MB: as a favicon it was squashed to a smear and downloaded in full
    // on every page load.
    icon: "/brand/corpusil-mark.png",
    shortcut: "/brand/corpusil-mark.png",
    apple: "/brand/corpusil-mark-180.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${uiFont.variable} ${editorialFont.variable}`}>
      <body>
        {children}
        <DesktopUpdater />
      </body>
    </html>
  );
}
