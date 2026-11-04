"use client";

import { CalendarClock, FilePlus2, FileText, Loader2, MessagesSquare } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { calendarAcrossCases, listDefenceAnalyses, listWork, readDefenceAnalysis } from "@/lib/api-advocate";
import { dayPhrase, eventStateMeta, formatDate, sortEvents, workKindLabel } from "@/lib/advocate-presentation";
import type { AgentCitation, DefenceAnalysisResponse } from "@/lib/types";
import type { AdvocateSource, CalendarEvent, WorkSummary } from "@/lib/types-advocate";
import { Badge, ErrorLine, errorText, SourceList } from "./shared";

const STRENGTH: Record<DefenceAnalysisResponse["evidence_strength"], { label: string; tone: "ok" | "warn" | "bad" }> = {
  strong: { label: "Strong: most proposed points passed", tone: "ok" },
  moderate: { label: "Moderate: some proposed points failed", tone: "warn" },
  insufficient: { label: "Insufficient: most proposed points failed", tone: "bad" },
};

function asSource(citation: AgentCitation): AdvocateSource {
  return {
    point_id: citation.chunk_id,
    chunk_id: citation.chunk_id,
    title: citation.title,
    source_type: citation.source_type,
    section: citation.section ?? null,
    page_start: citation.page_start,
    page_end: citation.page_end,
    excerpt: citation.excerpt,
    relevance_score: citation.retrieval_score ?? null,
    verification_status: citation.verification_status ?? "unverified",
    current_status: citation.current_status ?? "status_unverified",
    replaced_by: citation.replaced_by,
    repealed_on: citation.repealed_on,
    repeal_label: citation.repeal_label,
    section_mappings: citation.section_mappings,
    unmapped_repealed_provisions: citation.unmapped_repealed_provisions,
    mapping_review_status: citation.mapping_review_status,
    scope: citation.current_status === "not_applicable" ? "private_case" : "global",
    source_url: citation.source_url,
    court: citation.court,
  };
}

/** The analysis with what it rests on, so "verified" can be checked rather than taken on trust. */
export function DefenceAnalysisResult({ analysis }: { analysis: DefenceAnalysisResponse }) {
  const byId = useMemo(() => new Map(analysis.citations.map((item) => [item.chunk_id, asSource(item)])), [analysis.citations]);
  const strength = STRENGTH[analysis.evidence_strength];
  const repealed = analysis.citations.filter((item) => item.repeal_label === "no_longer_in_force");
  return (
    <div className="adv-section mt-6">
      <div className="adv-strength">
        <Badge tone={strength.tone}>Evidence strength. {strength.label}</Badge>
        <Badge tone="neutral">{analysis.points.length} shown</Badge>
        <Badge tone={analysis.rejected_point_count ? "warn" : "neutral"}>{analysis.rejected_point_count} failed the check, not shown</Badge>
        {analysis.version != null && <Badge tone="neutral">Version {analysis.version}, kept in this case</Badge>}
      </div>
      <div className="adv-notice is-plain"><span>{analysis.summary}</span></div>
      {!!repealed.length && (
        <div className="adv-notice is-bad" role="note">
          <strong>Repealed law is relied on below.</strong>
          {repealed.map((item) => <span key={item.chunk_id}>{item.title}{item.replaced_by ? `, replaced by ${item.replaced_by}` : ""}</span>)}
        </div>
      )}
      <ul className="adv-list">
        {analysis.points.map((point, index) => {
          const sources = point.source_chunk_ids.map((id) => byId.get(id)).filter((item): item is AdvocateSource => !!item);
          return (
            <li key={`${point.category}-${index}`} className="adv-card">
              <p className="adv-subhead">{point.category.replaceAll("_", " ")}</p>
              <p>{point.point}</p>
              <SourceList sources={sources} />
            </li>
          );
        })}
      </ul>
      <p className="adv-meta">{analysis.disclaimer}</p>
    </div>
  );
}

/**
 * The advocate's part of the case file: saved analyses that reopen as written,
 * the next dates in this case, and everything else generated for it.
 */
export function AdvocateCaseFile({
  caseId,
  refreshToken,
  onOpenAnalysis,
  onNewAnalysis,
  onOpenDesk,
}: {
  caseId: string;
  refreshToken?: unknown;
  onOpenAnalysis: (analysis: DefenceAnalysisResponse) => void;
  onNewAnalysis: () => void;
  onOpenDesk: () => void;
}) {
  const [analyses, setAnalyses] = useState<WorkSummary[] | null>(null);
  const [work, setWork] = useState<WorkSummary[] | null>(null);
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [failure, setFailure] = useState("");
  useEffect(() => {
    let cancelled = false;
    setAnalyses(null); setWork(null); setEvents(null);
    listDefenceAnalyses(caseId).then((response) => { if (!cancelled) setAnalyses(response.analyses); }).catch(() => undefined);
    listWork(caseId).then((response) => { if (!cancelled) setWork(response.work.filter((item) => item.kind !== "defence_analysis")); }).catch(() => undefined);
    calendarAcrossCases().then((response) => { if (!cancelled) setEvents(response.events.filter((item) => item.case_id === caseId)); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [caseId, refreshToken]);
  const open = async (id: string) => {
    setOpening(id);
    setFailure("");
    try {
      onOpenAnalysis(await readDefenceAnalysis(caseId, id));
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setOpening(null);
    }
  };
  return (
    <>
      <section className="case-block">
        <div className="case-block-head">
          <div>
            <h4>Defence analyses in this case</h4>
            <p>Each one is kept with the authorities it relied on, and opens as it was written.</p>
          </div>
          <button className="button-primary" onClick={onNewAnalysis}><FilePlus2 size={15} />New analysis</button>
        </div>
        {analyses?.length ? (
          <ul className="case-chats">
            {analyses.map((item) => (
              <li key={item.id}>
                <button onClick={() => void open(item.id)} disabled={opening === item.id}>
                  {opening === item.id ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
                  <span className="min-w-0 flex-1 truncate">Version {item.version}: {item.title}</span>
                  <span className="case-chat-when">{formatDate(item.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="case-empty">{analyses === null ? "Reading saved analyses…" : "No defence analysis has been run in this case yet."}</p>}
        <ErrorLine text={failure} />
      </section>
      <section className="case-block">
        <div className="case-block-head">
          <div>
            <h4>Dates and saved work</h4>
            <p>Hearings and limitation dates for this case, and what has been prepared for it.</p>
          </div>
          <button className="button-primary" onClick={onOpenDesk}><MessagesSquare size={15} />Open the advocate desk</button>
        </div>
        {events?.length ? (
          <ul className="case-chats">
            {sortEvents(events).slice(0, 4).map((event) => (
              <li key={event.id}>
                <button onClick={onOpenDesk}>
                  <CalendarClock size={14} />
                  <span className="min-w-0 flex-1 truncate">{event.title}</span>
                  <span className="case-flag">{eventStateMeta(event.state).label}</span>
                  <span className="case-chat-when">{formatDate(event.due_on)}, {dayPhrase(event.days_from_today)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="case-empty">{events === null ? "Reading dates…" : "No open date recorded for this case."}</p>}
        {!!work?.length && (
          <ul className="case-chats">
            {work.slice(0, 4).map((item) => (
              <li key={item.id}>
                <button onClick={onOpenDesk}>
                  <FileText size={14} />
                  <span className="min-w-0 flex-1 truncate">{workKindLabel(item.kind)}, version {item.version}</span>
                  <span className="case-chat-when">{formatDate(item.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
