"use client";

import { useEffect } from "react";
import LawLookup from "@/components/LawLookup";
import "./law.css";

export default function LawPage() {
  useEffect(() => {
    document.title = "Open a provision | Corpusil";
    if (!document.documentElement.dataset.theme && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      document.documentElement.dataset.theme = "ink";
    }
  }, []);
  return (
    <main className="law-page">
      <LawLookup />
    </main>
  );
}
