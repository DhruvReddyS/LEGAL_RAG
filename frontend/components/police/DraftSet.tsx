"use client";

import { Check, ClipboardCopy, Download, FilePlus2, FileText, Loader2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { errorText, ErrorNote, Field, Loading } from "@/components/police/shared";
import { createDraft, listDrafts, listSearches, readDraft } from "@/lib/api-police";
import { docxFilename, saveDocx, textToBlocks } from "@/lib/docx";
import { DRAFT_FIELDS, DRAFT_TITLES, draftForClipboard, formatMoment } from "@/lib/police-presentation";
import type { DraftSummary, DraftType, PoliceDraft, SearchRecordRow } from "@/lib/types-police";

const TYPES = Object.keys(DRAFT_TITLES) as DraftType[];

function DraftView({ draft }: { draft: PoliceDraft }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const text = draftForClipboard(draft);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true); window.setTimeout(() => setCopied(false), 2000); }
    catch { setError("The browser refused clipboard access. Select the text and copy it instead."); }
  };
  const save = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `DRAFT-${draft.draft_type}-v${draft.version}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="police-stack">
      <div className="police-draft-banner" role="note">
        Draft, version {draft.version}. Not signed, not issued, not filed.
        <span className="ml-auto flex flex-wrap gap-1.5">
          <button type="button" className="police-mini" onClick={() => void copy()}>{copied ? <Check size={13} aria-hidden="true" /> : <ClipboardCopy size={13} aria-hidden="true" />}{copied ? "Copied" : "Copy"}</button>
          <button type="button" className="police-mini" onClick={save}><Download size={13} aria-hidden="true" />Save</button>
          <button type="button" className="police-mini" onClick={() => saveDocx(docxFilename(`DRAFT-${draft.draft_type}`, draft.version), textToBlocks(text))}><FileText size={13} aria-hidden="true" />Save as Word</button>
        </span>
      </div>
      <ErrorNote message={error} />
      {draft.missing_fields.length > 0 && (
        <p className="police-note"><strong>Still to complete ({draft.missing_fields.length}):</strong> {draft.missing_fields.join(", ")}.</p>
      )}
      <p className="police-chips" aria-label="Provisions used">
        {draft.provisions.map((provision) => <span key={provision} className="provision-tag">{provision}</span>)}
      </p>
      <pre className="police-draft-text" tabIndex={0}>{draft.rendered_text}</pre>
    </div>
  );
}

export function DraftSet({ caseId }: { caseId: string }) {
  const [type, setType] = useState<DraftType>("s35_3_notice");
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [drafts, setDrafts] = useState<DraftSummary[] | null>(null);
  const [searches, setSearches] = useState<SearchRecordRow[]>([]);
  const [shown, setShown] = useState<PoliceDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [rows, recorded] = await Promise.all([listDrafts(caseId), listSearches(caseId)]);
      setDrafts(rows); setSearches(recorded);
    } catch (cause) { setError(errorText(cause)); }
  }, [caseId]);
  useEffect(() => { void load(); }, [load]);

  const generate = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const cleaned = Object.fromEntries(Object.entries(inputs).filter(([, value]) => value.trim()));
      const made = await createDraft(caseId, type, cleaned);
      setShown(made);
      await load();
    } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  };
  const open = async (id: string) => {
    setError("");
    // Read back rather than generated again: a draft someone reviewed must not change.
    try { setShown(await readDraft(caseId, id)); }
    catch (cause) { setError(errorText(cause)); }
  };

  return (
    <div className="police-stack">
      <p className="police-note">
        Filled from what is on record for this case, by template and not by a model. Anything missing is marked in the text and listed. Nothing here is filed or sent anywhere, and each generation is kept as its own version.
      </p>
      <form className="police-form" onSubmit={generate} aria-label="Generate a draft">
        <div className="police-grid">
          <Field label="Document">
            <select className="field" value={type} onChange={(e) => { setType(e.target.value as DraftType); setInputs({}); }}>
              {TYPES.map((key) => <option key={key} value={key}>{DRAFT_TITLES[key]}</option>)}
            </select>
          </Field>
          {type === "seizure_memo" && (
            <Field label="From a recorded search" hint="Takes the place, time and the exhibits linked to that search.">
              <select className="field" value={inputs.search_id ?? ""} onChange={(e) => setInputs((c) => ({ ...c, search_id: e.target.value }))}>
                <option value="">None chosen: all exhibits</option>
                {searches.map((search) => <option key={search.id} value={search.id}>{search.place}</option>)}
              </select>
            </Field>
          )}
          {DRAFT_FIELDS[type].filter((f) => !f.long).map((field) => (
            <Field key={field.key} label={field.label}>
              <input className="field" value={inputs[field.key] ?? ""} onChange={(e) => setInputs((c) => ({ ...c, [field.key]: e.target.value }))} />
            </Field>
          ))}
        </div>
        {DRAFT_FIELDS[type].filter((f) => f.long).map((field) => (
          <Field key={field.key} label={field.label}>
            <textarea className="field" value={inputs[field.key] ?? ""} onChange={(e) => setInputs((c) => ({ ...c, [field.key]: e.target.value }))} />
          </Field>
        ))}
        <ErrorNote message={error} />
        <div>
          <button className="button-primary" disabled={busy} type="submit">
            {busy ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <FilePlus2 size={15} aria-hidden="true" />}Generate draft
          </button>
        </div>
      </form>

      {shown && <DraftView draft={shown} />}

      {drafts === null && !error && <Loading />}
      {drafts && drafts.length > 0 && (
        <section className="police-section" aria-label="Drafts in this case">
          <div className="police-section-head"><h4>Drafts in this case</h4><b>{drafts.length}</b></div>
          <ul className="case-chats">
            {drafts.map((draft) => (
              <li key={draft.id}>
                <button type="button" onClick={() => void open(draft.id)}>
                  <FileText size={14} aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">DRAFT: {draft.title}, version {draft.version}</span>
                  {draft.missing_field_count > 0 && <span className="case-flag">{draft.missing_field_count} to complete</span>}
                  <span className="case-chat-when">{formatMoment(draft.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
