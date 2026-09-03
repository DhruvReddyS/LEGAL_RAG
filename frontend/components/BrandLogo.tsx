"use client";
import { useId } from "react";
/** Retain the original artwork; remove its paper field at render time. */
export default function BrandLogo({ className = "" }: { className?: string }) {
  const filter = "logo-" + useId().replaceAll(":", "");
  return <div className={`corpusil-wordmark ${className}`}><svg viewBox="115 185 1545 370" role="img" aria-label="Corpusil" style={{display:"block",width:"100%",overflow:"hidden"}}><defs><filter id={filter} colorInterpolationFilters="sRGB"><feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  -3 -3 -3 0 8" result="cutout"/><feFlood floodColor="currentColor" result="brand"/><feComposite in="brand" in2="cutout" operator="in"/></filter></defs><image href="/brand/corpusil-logo.png" width="1774" height="887" filter={`url(#${filter})`} /></svg></div>;
}
