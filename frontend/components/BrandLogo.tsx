/**
 * The wordmark, set in the product's own serif beside a plain scales mark. Drawn, not an
 * image: the raster it replaces blurred at sidebar size and put glyphs inside the letters.
 */
export function BrandMark({ size = 22 }: { size?: number }) {
  return <svg className="corpusil-mark" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3v17.5M8 20.5h8M5 6.5h14" />
    <path d="M5 6.5 2.25 13.5M5 6.5l2.75 7M19 6.5l-2.75 7M19 6.5l2.75 7" />
    <path d="M2 13.5a3 3 0 0 0 6 0zM16 13.5a3 3 0 0 0 6 0z" />
  </svg>;
}

export default function BrandLogo({ className = "" }: { className?: string }) {
  return <span className={`corpusil-wordmark ${className}`} role="img" aria-label="Corpusil"><BrandMark /><span aria-hidden="true">Corpusil</span></span>;
}
