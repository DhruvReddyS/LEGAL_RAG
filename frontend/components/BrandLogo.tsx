/**
 * The real logo, cut from public/brand/corpusil-logo.png without its tagline and with a
 * transparent background. Dark screens get a version with cream letters, because the logo's
 * own ink would disappear on them. The artwork comes from that file and is never redrawn.
 */
export default function BrandLogo({ className = "" }: { className?: string }) {
  return <span className={`corpusil-wordmark ${className}`} role="img" aria-label="Corpusil">
    {/* eslint-disable-next-line @next/next/no-img-element -- a static export has no image optimiser */}
    <img className="corpusil-logo-ink" src="/brand/corpusil-wordmark.png" alt="" width={880} height={204} />
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img className="corpusil-logo-cream" src="/brand/corpusil-wordmark-light.png" alt="" width={880} height={204} />
  </span>;
}
