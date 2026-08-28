import type { Metadata } from "next";
import DesktopUpdater from "@/components/DesktopUpdater";
import "./globals.css";

export const metadata: Metadata = {
  title: "Legal RAG — Global Legal Corpus",
  description: "Search and explore India's global legal corpus",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans">
        {children}
        <DesktopUpdater />
      </body>
    </html>
  );
}
