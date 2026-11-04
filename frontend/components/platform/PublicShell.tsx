import Link from "next/link";
import type { ReactNode } from "react";
import BrandLogo from "@/components/BrandLogo";
import { APP_HREF, SITE_NAV, SITE_ROUTES, SOURCE_URL } from "@/lib/site";
import SiteThemeToggle from "./SiteThemeToggle";

export default function PublicShell({ children, tone = "paper" }: { children: ReactNode; tone?: "paper" | "cover" }) {
  return (
    <div className="site" data-header-tone={tone}>
      <a className="skip-link" href="#content">Skip to content</a>
      <header className="site-header">
        <Link href={SITE_ROUTES.welcome} className="site-brand" aria-label="Corpusil home"><BrandLogo /></Link>
        <nav className="site-nav" aria-label="Site">
          {SITE_NAV.map(item => <Link key={item.href} href={item.href}>{item.label}</Link>)}
        </nav>
        <div className="site-header-end">
          <SiteThemeToggle />
          <Link href={APP_HREF} className="site-open-app">Open the app</Link>
        </div>
      </header>
      <main id="content">{children}</main>
      <footer className="site-footer">
        <p className="site-footer-note">
          Corpusil gives legal information with its sources. It does not give legal advice, predict outcomes or
          replace an advocate. For help with your own matter, call the National Legal Services Authority on{" "}
          <a href="tel:15100">15100</a> or ask at your district court.
        </p>
        <nav aria-label="Footer" className="site-footer-nav">
          <Link href={SITE_ROUTES.welcome}>About</Link>
          {SITE_NAV.map(item => <Link key={item.href} href={item.href}>{item.label}</Link>)}
          <Link href={APP_HREF}>Open the app</Link>
          <a href={SOURCE_URL} rel="noopener noreferrer">Source code</a>
        </nav>
      </footer>
    </div>
  );
}

/** A plain text page: privacy, terms and help share this measure and rhythm. */
export function DocumentPage({ eyebrow, title, lede, children }: { eyebrow: string; title: string; lede?: ReactNode; children: ReactNode }) {
  return (
    <article className="doc">
      <header className="doc-head">
        <p className="doc-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {lede && <p className="doc-lede">{lede}</p>}
      </header>
      <div className="doc-body">{children}</div>
    </article>
  );
}
