"use client";

import LawLookup from "@/components/LawLookup";
import "@/app/law/law.css";

/** The same lookup as the public /law page, kept inside the navigation. */
export default function LawScreen() {
  return (
    <div className="pro-law">
      <LawLookup />
    </div>
  );
}
