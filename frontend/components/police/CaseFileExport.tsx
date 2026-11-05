"use client";

import { Download, FileOutput, FileText, Loader2, Printer } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { errorText, ErrorNote } from "@/components/police/shared";
import { getAccessLog, getCaseFile } from "@/lib/api-police";
import { htmlToBlocks, saveDocx } from "@/lib/docx";
import { formatMoment } from "@/lib/police-presentation";
import type { CaseFile } from "@/lib/types-police";

export function CaseFileExport({ caseId }: { caseId: string }) {
  const [contact, setContact] = useState(false);
  const [drafts, setDrafts] = useState(true);
  const [file, setFile] = useState<CaseFile | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [access, setAccess] = useState<{ at: string; who: string; what: string }[] | null>(null);
  const frame = useRef<HTMLIFrameElement>(null);

  useEffect(() => { getAccessLog(caseId).then(setAccess).catch(() => setAccess(null)); }, [caseId]);

  const build = useCallback(async () => {
    setBusy(true); setError("");
    try { setFile(await getCaseFile(caseId, { contact, drafts })); }
    catch (cause) { setFile(null); setError(errorText(cause)); } finally { setBusy(false); }
  }, [caseId, contact, drafts]);

  const print = () => frame.current?.contentWindow?.print();
  const save = () => {
    if (!file) return;
    const url = URL.createObjectURL(new Blob([file.html], { type: "text/html;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `case-file-${file.generated_at.slice(0, 10)}.html`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="police-stack">
      <p className="police-note">
        A compilation of this case&apos;s facts, timeline, compliance, inventory, custody log, witnesses, searches and drafts, laid out to print or save as a PDF. It says on its face that it is not a filed document. Each export is logged.
      </p>
      <div className="police-filters">
        <label className="is-check"><input type="checkbox" checked={drafts} onChange={(e) => setDrafts(e.target.checked)} />Include the latest drafts, marked as drafts</label>
        <label className="is-check"><input type="checkbox" checked={contact} onChange={(e) => setContact(e.target.checked)} />Include witness contact details</label>
        <button type="button" className="button-primary" disabled={busy} onClick={() => void build()}>
          {busy ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <FileOutput size={15} aria-hidden="true" />}Compile the case file
        </button>
      </div>
      <ErrorNote message={error} />
      {file && (
        <>
          <div className="police-row-actions">
            <button type="button" className="police-mini" onClick={print}><Printer size={13} aria-hidden="true" />Print or save as PDF</button>
            <button type="button" className="police-mini" onClick={save}><Download size={13} aria-hidden="true" />Save the HTML</button>
            <button type="button" className="police-mini" onClick={() => saveDocx(`case-file-${file.generated_at.slice(0, 10)}.docx`, htmlToBlocks(file.html))}><FileText size={13} aria-hidden="true" />Save as Word</button>
            <span className="police-note">Compiled {formatMoment(file.generated_at)}.</span>
          </div>
          {file.missing_sections.length > 0 && (
            <p className="police-note"><strong>Nothing on record for:</strong> {file.missing_sections.join(", ")}. The file says so in each place.</p>
          )}
          {/* No scripts may run in here: it is free text typed by people, escaped by the
              server, and the sandbox is the second line. Same-origin is only for print. */}
          <iframe
            ref={frame}
            className="police-file-frame"
            title="Case file preview"
            sandbox="allow-same-origin allow-modals"
            srcDoc={file.html}
          />
        </>
      )}
      <section className="police-section" aria-label="Supervisor views of this case">
        <div className="police-section-head">
          <h4>Who else has looked</h4>
          <small>A supervisor sees counts and deadline states, never evidence or witnesses. Every look is listed here.</small>
        </div>
        {access === null ? (
          <p className="police-note">The access log could not be read.</p>
        ) : access.length ? (
          <ul className="grid gap-1">
            {access.slice(0, 20).map((entry) => (
              <li key={`${entry.at}-${entry.who}`} className="police-row-detail">{formatMoment(entry.at)}: {entry.who}. {entry.what}.</li>
            ))}
          </ul>
        ) : (
          <p className="police-note">No supervisor has viewed this case.</p>
        )}
      </section>
    </div>
  );
}
