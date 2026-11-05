"use client";

import { Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { getLawChangeNotices } from "@/lib/api-corpus-lifecycle";

/**
 * The notices themselves sit two clicks down in Account and privacy, where nobody
 * would look unprompted. This is the prompt. A failed read stays quiet: the notices
 * are still there, and nothing on this screen depends on them.
 */
export default function LawChangeStrip({ text, action, refresh, onOpen }: { text: string; action: string; refresh: unknown; onOpen: () => void }) {
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    let cancelled = false;
    getLawChangeNotices()
      .then(body => { if (!cancelled) setUnread(body.notices.filter(item => !item.read_at).length); })
      .catch(() => { if (!cancelled) setUnread(0); });
    return () => { cancelled = true; };
  }, [refresh]);
  if (!unread) return null;
  return (
    <div className="law-change-strip" role="status">
      <Scale size={14} aria-hidden="true" className="flex-none" />
      <span className="min-w-0 flex-1">{text}</span>
      <button type="button" onClick={onOpen}>{action}</button>
    </div>
  );
}
