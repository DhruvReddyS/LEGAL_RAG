"use client";

import { FileText, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { listWork, readWork } from "@/lib/api-advocate";
import { formatDate, workKindLabel, workView } from "@/lib/advocate-presentation";
import type { DefenceAnalysisResponse } from "@/lib/types";
import type { BailAssessment, BriefContent, ComparisonContent, DebateContent, DraftContent, OpponentResult, WorkDetail, WorkSummary } from "@/lib/types-advocate";
import { BailAssessmentView } from "./BailTool";
import { BriefView } from "./BriefTool";
import { DebateView } from "./DebateTool";
import { DefenceAnalysisResult } from "./DefenceAnalysisResult";
import { DraftView } from "./DraftingTool";
import { ComparisonView, OpponentResultView } from "./ResearchTools";
import { ErrorLine, errorText } from "./shared";

function WorkBody({ work }: { work: WorkDetail<unknown> }) {
  switch (workView(work.kind)) {
    case "draft": return <DraftView work={work as WorkDetail<DraftContent>} />;
    case "brief": return <BriefView work={work as WorkDetail<BriefContent>} />;
    case "bail": return <BailAssessmentView result={work.content as BailAssessment} />;
    case "comparison": return <ComparisonView work={work as WorkDetail<ComparisonContent>} />;
    case "opponent": return <OpponentResultView result={work.content as OpponentResult} />;
    case "debate": return <DebateView debate={work.content as DebateContent} />;
    case "defence": return <DefenceAnalysisResult analysis={work.content as DefenceAnalysisResponse} />;
    default: return <p className="case-empty">This saved item has a kind this version cannot display.</p>;
  }
}

export default function SavedWork({ caseId }: { caseId: string }) {
  const [rows, setRows] = useState<WorkSummary[] | null>(null);
  const [open, setOpen] = useState<WorkDetail<unknown> | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [failure, setFailure] = useState("");
  useEffect(() => {
    listWork(caseId).then((response) => setRows(response.work)).catch((error) => setFailure(errorText(error)));
  }, [caseId]);
  const show = async (id: string) => {
    setOpening(id);
    setFailure("");
    try {
      setOpen(await readWork(caseId, id));
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setOpening(null);
    }
  };
  return (
    <div className="adv-section">
      <p className="adv-lede">Everything generated for this case, kept as it was written. Opening one reruns nothing. A new run is a new version.</p>
      <ErrorLine text={failure} />
      {rows && !rows.length && <p className="case-empty">Nothing has been saved in this case yet.</p>}
      {!!rows?.length && (
        <ul className="adv-list">
          {rows.map((row) => (
            <li key={row.id}>
              <button type="button" className="adv-row-button" aria-current={open?.id === row.id} onClick={() => void show(row.id)}>
                {opening === row.id ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} aria-hidden="true" />}
                <span className="adv-grow">{workKindLabel(row.kind)}, version {row.version}<span className="adv-meta" style={{ display: "block" }}>{row.title}</span></span>
                {row.status === "incomplete" && <span className="case-flag">Incomplete</span>}
                <span className="adv-meta">{formatDate(row.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && <WorkBody work={open} />}
    </div>
  );
}
