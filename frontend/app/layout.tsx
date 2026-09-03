import type { Metadata } from "next";
import { DM_Sans, Newsreader } from "next/font/google";
import DesktopUpdater from "@/components/DesktopUpdater";
import "./globals.css";
const uiFont = DM_Sans({ subsets: ["latin"], variable: "--font-ui", display: "swap" });
const editorialFont = Newsreader({ subsets: ["latin"], variable: "--font-editorial", display: "swap", adjustFontFallback: false });

export const metadata: Metadata = {
  title: {
    default: "Corpusil",
    template: "%s | Corpusil",
  },
  description: "Evidence-led legal research and decision support for India.",
  icons: {
    icon: "/brand/corpusil-logo.png",
    shortcut: "/brand/corpusil-logo.png",
    apple: "/brand/corpusil-logo.png",
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
