"use client";

import { Scale } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  getLawChangeNotices,
  markAllLawChangesRead,
  markLawChangeRead,
  type LawChangeNotice,
} from "@/lib/api-corpus-lifecycle";
import { describeLawChange } from "@/lib/law-change-text";

/** Says nothing at all until there is something to say. A failed load stays quiet too. */
export default function LawChangeNotices() {
  const [notices, setNotices] = useState<LawChangeNotice[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getLawChangeNotices()
      .then(body => setNotices(body.notices.filter(item => !item.read_at)))
      .catch(() => setNotices([]));
  }, []);
  useEffect(load, [load]);

  if (!notices.length) return null;

  const dismiss = async (run: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await run();
      load();
    } catch {
      // It stays unread and is offered again. Nothing was lost.
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="recovery-codes" aria-labelledby="law-change-title">
      <h3 id="law-change-title" style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <Scale size={15} aria-hidden="true" /> The law behind a saved answer has changed
      </h3>
      <ul style={{ gridTemplateColumns: "minmax(0, 1fr)", gap: 10 }}>
        {notices.map(notice => (
          <li key={notice.id}>
            <p className="acct-hint">
              Your conversation <strong>{notice.conversation_title}</strong> relied on{" "}
              <strong>{notice.document_title}</strong>. {describeLawChange(notice)} Check that answer again before relying on it.
            </p>
            {notice.basis && <p className="acct-hint">{notice.basis}</p>}
            <button type="button" className="button-secondary" disabled={busy} onClick={() => dismiss(() => markLawChangeRead(notice.id))}>
              Mark as read
            </button>
          </li>
        ))}
      </ul>
      {notices.length > 1 && (
        <button type="button" className="button-secondary" disabled={busy} onClick={() => dismiss(markAllLawChangesRead)}>
          Mark all as read
        </button>
      )}
    </section>
  );
}
