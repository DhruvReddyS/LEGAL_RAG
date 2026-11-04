"use client";

import { FileText, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { listIndexedCaseDocuments } from "@/lib/api";
import { createBrief } from "@/lib/api-advocate";
import type { CaseDocumentSummary } from "@/lib/types";
import type { BriefContent, WorkDetail } from "@/lib/types-advocate";
import { CheckRows, ClaimList, ErrorLine, errorText, Notes } from "./shared";

export function BriefView({ work }: { work: WorkDetail<BriefContent> }) {
  const { content } = work;
  const flagged = content.provisions_in_record.filter((row) => row.needs_attention);
  return (
    <div className="adv-section">
      <h4 className="adv-heading">{content.kind === "synopsis" ? "Synopsis" : "Brief"}, version {work.version}</h4>
      <Notes items={[content.note, content.disclaimer]} />
      {content.partial_review && (
        <div className="adv-notice" role="note">
          <strong>Partial review.</strong>
          <span>{content.passages_read} of {content.passages_total} passages were read, selected evenly across {content.documents_read} document(s). What is not here may still be in the file.</span>
        </div>
      )}
      {!content.sections.length && <p className="case-empty">Nothing proposed passed the check against the case documents, so nothing is shown.</p>}
      {content.sections.map((section) => (
        <section key={section.key} className="adv-section">
          <p className="adv-subhead">{section.title}</p>
          <ClaimList claims={section.claims} />
        </section>
      ))}
      {!!flagged.length && (
        <section className="adv-section">
          <p className="adv-subhead">Provisions the record cites that need attention</p>
          <CheckRows rows={flagged} />
        </section>
      )}
    </div>
  );
}

export default function BriefTool({ caseId }: { caseId: string }) {
  const [documents, setDocuments] = useState<CaseDocumentSummary[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [kind, setKind] = useState<"brief" | "synopsis">("brief");
  const [focus, setFocus] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [work, setWork] = useState<WorkDetail<BriefContent> | null>(null);
  useEffect(() => {
    listIndexedCaseDocuments(caseId).then((response) => setDocuments(response.documents)).catch((error) => setFailure(errorText(error)));
  }, [caseId]);
  const run = async () => {
    setBusy(true);
    setFailure("");
    try {
      setWork(await createBrief(caseId, { kind, document_ids: chosen, focus: focus.trim() || undefined }));
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="adv-section">
      <p className="adv-lede">
        Built only from the documents in this case. Each statement is checked against the passage cited for it, and any that
        fails is left out and counted. It adds no law and no view on the merits.
      </p>
      <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <fieldset className="adv-fieldset">
          <legend>What to prepare</legend>
          <div className="adv-checks">
            <label className="adv-check"><input type="radio" name="brief-kind" checked={kind === "brief"} onChange={() => setKind("brief")} />Brief</label>
            <label className="adv-check"><input type="radio" name="brief-kind" checked={kind === "synopsis"} onChange={() => setKind("synopsis")} />Synopsis: dates, issues, relief</label>
          </div>
        </fieldset>
        <fieldset className="adv-fieldset">
          <legend>Documents</legend>
          {documents === null ? <p className="adv-meta">Reading the case file…</p> : documents.length ? (
            <>
              <div className="adv-checks">
                {documents.map((item) => (
                  <label key={item.document_id} className="adv-check">
                    <input
                      type="checkbox"
                      checked={chosen.includes(item.document_id)}
                      onChange={() => setChosen((current) => current.includes(item.document_id) ? current.filter((id) => id !== item.document_id) : [...current, item.document_id])}
                    />
                    {item.filename}
                  </label>
                ))}
              </div>
              <small className="adv-meta">Leave all clear to use every document.</small>
            </>
          ) : <p className="case-empty">No document has been added to this case yet. Use Add evidence first.</p>}
        </fieldset>
        <label className="adv-label">Focus (optional)
          <input className="field" value={focus} maxLength={2000} onChange={(event) => setFocus(event.target.value)} placeholder="The bail hearing on the 14th" />
        </label>
        <div className="adv-actions">
          <button type="submit" className="button-primary" disabled={busy || !documents?.length}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}Prepare
          </button>
          {busy && <span className="adv-meta">Reading the file and checking each statement. This can take a few minutes.</span>}
        </div>
        <ErrorLine text={failure} />
      </form>
      {work && <BriefView work={work} />}
    </div>
  );
}
