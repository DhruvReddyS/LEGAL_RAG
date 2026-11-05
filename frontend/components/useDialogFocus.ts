"use client";
import { useEffect, useRef } from "react";

export function useDialogFocus(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  // Read during render: an autoFocus inside the dialog has moved focus by the time an effect runs.
  const opener = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  if (open && !wasOpen.current && typeof document !== "undefined") opener.current = document.activeElement as HTMLElement | null;
  wasOpen.current = open;
  useEffect(() => {
    if (!open) return;
    const nodes = () => Array.from(ref.current?.querySelectorAll<HTMLElement>("input, button, select, textarea, summary, a[href], [tabindex='0']") ?? []).filter(node => !node.hasAttribute("disabled") && node.getClientRects().length > 0);
    if (!ref.current?.contains(document.activeElement)) nodes()[0]?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.stopPropagation(); closeRef.current(); }
      if (event.key === "Tab") {
        const items = nodes(); const first = items[0]; const last = items[items.length - 1];
        if (!ref.current?.contains(document.activeElement)) { event.preventDefault(); first?.focus(); }
        else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => { document.removeEventListener("keydown", handleKey); opener.current?.focus(); };
  }, [open]);
  return ref;
}
