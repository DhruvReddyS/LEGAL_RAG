"use client";

import { FilePlus2, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { createAdvocateDraft, listDraftTemplates } from "@/lib/api-advocate";
import { formatDate } from "@/lib/advocate-presentation";
import type { DraftContent, DraftTemplateInfo, WorkDetail } from "@/lib/types-advocate";
import { CheckRows, ClaimList, CurrencyBadge, DraftActions, ErrorLine, errorText, Notes, SourceList } from "./shared";

export function DraftView({ work }: { work: WorkDetail<DraftContent> }) {
  const { content } = work;
  const flagged = content.authority_checks.filter((row) => row.needs_attention);
  return (
    <div className="adv-section">
      <div className="adv-card-head">
        <h4 className="adv-heading">{content.title}, version {work.version}</h4>
        <DraftActions content={content} title={content.title} version={work.version} />
      </div>
      <div className="adv-notice" role="note">
        <strong>Draft for review.</strong>
        <span>{content.disclaimer}</span>
        {!!content.missing_fields.length && <span>Still to fill in: {content.missing_fields.join(", ")}.</span>}
      </div>
      {content.computed_limit && (
        <p className="adv-date">
          <span className="adv-grow"><strong>{formatDate(content.computed_limit.date)}</strong> <span className="adv-meta">{content.computed_limit.label}: {content.computed_limit.computed_from}, {content.computed_limit.provision}</span></span>
        </p>
      )}
      <Notes items={content.notes} />
      {!!flagged.length && (
        <div className="adv-section">
          <p className="adv-subhead">Citations in this draft that need attention before filing</p>
          <CheckRows rows={flagged} />
        </div>
      )}
      <pre className="adv-pre">{content.rendered_text}</pre>
      {!!content.statutory_provisions.length && (
        <div><p className="adv-subhead">Provision relied on</p><SourceList sources={content.statutory_provisions} /></div>
      )}
      {!!content.grounds.length && (
        <div className="adv-section">
          <p className="adv-subhead">Grounds, each checked against its passage</p>
          <ClaimList claims={content.grounds} ordered />
        </div>
      )}
      {!!content.authorities.length && (
        <div className="adv-section">
          <p className="adv-subhead">Authorities retrieved for review</p>
          <ul className="adv-list">
            {content.authorities.map((source) => {
              const problems = (source.authority_check ?? []).filter((row) => row.needs_attention);
              return (
                <li key={source.chunk_id} className="adv-card">
                  <div className="adv-card-head">
                    <p>{source.title}{source.section ? `, ${source.section}` : ""}</p>
                    <CurrencyBadge source={source} />
                  </div>
                  <SourceList sources={[source]} />
                  {!!problems.length && <CheckRows rows={problems} />}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function DraftingTool({ caseId }: { caseId: string }) {
  const [templates, setTemplates] = useState<DraftTemplateInfo[] | null>(null);
  const [selected, setSelected] = useState("bail_application");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [facts, setFacts] = useState("");
  const [instructions, setInstructions] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [work, setWork] = useState<WorkDetail<DraftContent> | null>(null);
  useEffect(() => {
    listDraftTemplates().then((response) => setTemplates(response.templates)).catch((error) => setFailure(errorText(error)));
  }, []);
  const template = templates?.find((item) => item.key === selected);
  const run = async () => {
    if (!template) return;
    setBusy(true);
    setFailure("");
    try {
      const chosen = Object.fromEntries(template.fields.map((field) => [field.name, fields[field.name] ?? ""]));
      setWork(await createAdvocateDraft(caseId, { draft_type: template.key, fields: chosen, facts, instructions: instructions || undefined }));
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="adv-section">
      <p className="adv-lede">
        The form and the statutory anchor are fixed. Grounds come from retrieved passages and only those that pass a check
        against their passage appear, with every authority run through the citation check. Nothing is inserted from memory.
      </p>
      <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <label className="adv-label">Document
          <select className="field" value={selected} onChange={(event) => setSelected(event.target.value)}>
            {(templates ?? []).map((item) => <option key={item.key} value={item.key}>{item.title}</option>)}
          </select>
          {template && <small>{template.description}</small>}
        </label>
        {template && (
          <div className="adv-grid">
            {template.fields.map((field) => {
              const label = `${field.label}${field.required ? "" : " (optional)"}`;
              const value = fields[field.name] ?? "";
              const change = (next: string) => setFields((current) => ({ ...current, [field.name]: next }));
              if (field.options.length) {
                return (
                  <label key={field.name} className="adv-label">{label}
                    <select className="field" value={value} onChange={(event) => change(event.target.value)}>
                      <option value="">Choose</option>
                      {field.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                );
              }
              return (
                <label key={field.name} className="adv-label" style={field.long ? { gridColumn: "1 / -1" } : undefined}>{label}
                  {field.long
                    ? <textarea className="field min-h-20 resize-y" value={value} onChange={(event) => change(event.target.value)} />
                    : <input className="field" type={field.kind === "date" ? "date" : "text"} value={value} onChange={(event) => change(event.target.value)} />}
                </label>
              );
            })}
          </div>
        )}
        {template?.uses_grounds && (
          <>
            <label className="adv-label">Facts as instructed
              <textarea className="field min-h-32 resize-y leading-6" value={facts} maxLength={12000} onChange={(event) => setFacts(event.target.value)} placeholder="The facts as your client gives them. They go into the draft as instructions, not as findings." />
            </label>
            <label className="adv-label">Your note on the grounds (optional)
              <input className="field" value={instructions} maxLength={2000} onChange={(event) => setInstructions(event.target.value)} />
            </label>
          </>
        )}
        <div className="adv-actions">
          <button type="submit" className="button-primary" disabled={busy || !template || (template.uses_grounds && facts.trim().length < 20)}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <FilePlus2 size={15} />}Prepare the draft
          </button>
          {busy && template?.uses_grounds && <span className="adv-meta">Finding authority and checking each ground. This can take a few minutes.</span>}
        </div>
        <ErrorLine text={failure} />
      </form>
      {work && <DraftView work={work} />}
    </div>
  );
}
