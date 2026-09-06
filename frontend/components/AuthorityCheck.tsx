"use client";

import { AlertTriangle, ArrowRight, CircleHelp, Loader2, ScanText, ShieldCheck, Slash } from "lucide-react";
import { useState } from "react";

import { checkDraftAuthorities } from "@/lib/api";
import type { AuthorityCheckResult, AuthorityFinding, CitationCheck } from "@/lib/types";

const FINDING: Record<AuthorityFinding, { label: string; Icon: typeof ShieldCheck; cls: string }> = {
  still_current: { label: "In force", Icon: ShieldCheck, cls: "authority-current" },
  renumbered: { label: "Renumbered", Icon: ArrowRight, cls: "authority-moved" },
  elements_changed: { label: "Changed", Icon: AlertTriangle, cls: "authority-changed" },
  not_re_enacted: { label: "Repealed, no successor", Icon: Slash, cls: "authority-gone" },
  no_mapping_known: { label: "No counterpart listed", Icon: CircleHelp, cls: "authority-changed" },
  not_checked: { label: "Not checked", Icon: CircleHelp, cls: "authority-unchecked" },
};

/**
 * Ordered by what a drafter has to do about it, not alphabetically.
 *
 * A provision that was repealed without replacement cannot be fixed by
 * substituting a number, so it goes first; a renumbering is a find-and-
 * replace and goes below the ones that need judgement.
 */
const ORDER: AuthorityFinding[] = [
  "not_re_enacted",
  "elements_changed",
  "no_mapping_known",
  "renumbered",
  "not_checked",
  "still_current",
];

export function AuthorityCheck({ caseId }: { caseId: string }) {
  const [draft, setDraft] = useState("");
  const [result, setResult] = useState<AuthorityCheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const run = async () => {
    if (!caseId || draft.trim().length < 10) return;
    setBusy(true);
    setNotice("");
    try {
      setResult(await checkDraftAuthorities(caseId, draft));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not check this draft.");
    } finally {
      setBusy(false);
    }
  };

  const rows: CitationCheck[] = result
    ? [...result.checked].sort((a, b) => ORDER.indexOf(a.finding) - ORDER.indexOf(b.finding))
    : [];

  return (
    <div className="space-y-4">
      <p className="max-w-3xl text-xs leading-5 text-[#827b8c]">
        Paste a draft. Every provision it cites is checked against the codes in force
        using the official concordance — no model reads the text. The three 2023 codes
        renumbered most of the IPC, CrPC and Evidence Act on 1 July 2024, and a few
        provisions were repealed without any successor at all.
      </p>

      <textarea
        value={draft}
        onChange={event => setDraft(event.target.value)}
        placeholder="Paste the petition, FIR, application or notice…"
        className="min-h-40 w-full resize-y rounded-xl border border-[#ddd6e5] p-4 text-sm leading-6 outline-none focus:border-[#897499] focus:ring-4 focus:ring-[#897499]/10"
      />

      <div className="flex flex-wrap items-center gap-3">
        <button onClick={run} disabled={busy || draft.trim().length < 10} className="button-primary">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <ScanText size={15} />}
          Check citations
        </button>
        {notice && <span className="text-xs text-[#b42318]">{notice}</span>}
      </div>

      {result && (
        <>
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-md bg-[#f1edf6] px-2 py-1 text-[#54515d]">{result.checked.length} citations found</span>
            {result.needs_attention > 0 && (
              <span className="rounded-md bg-[#fff5f4] px-2 py-1 font-medium text-[#b42318]">{result.needs_attention} need attention</span>
            )}
            {result.not_checked > 0 && (
              <span className="rounded-md bg-[#faf7f2] px-2 py-1 font-medium text-[#8a5a12]">{result.not_checked} outside the concordance</span>
            )}
          </div>

          {!result.checked.length && (
            <p className="rounded-xl border border-[#e9e5ef] p-4 text-xs text-[#827b8c]">
              No statutory citation was recognised in this text. That is not a finding
              that the draft cites nothing — check that provisions are written in a
              form the parser reads, such as &ldquo;section 438 of the Code of Criminal Procedure&rdquo;.
            </p>
          )}

          <ul className="space-y-2">
            {rows.map(row => {
              const shown = FINDING[row.finding];
              return (
                <li key={row.citation} className={`rounded-xl border p-3.5 ${shown.cls}`}>
                  <div className="flex items-start gap-2.5">
                    <shown.Icon size={16} className="mt-0.5 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                        <p className="font-mono text-sm text-[#54515d]">{row.citation}</p>
                        <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide">{shown.label}</span>
                      </div>
                      <p className="mt-1.5 text-xs leading-5">{row.advice}</p>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          <p className="text-[11px] leading-4 text-[#75817b]">
            The concordance covers the IPC, CrPC and Evidence Act only. Citations to other
            statutes are listed as unchecked rather than omitted, so a partial check is not
            mistaken for a complete one.
          </p>
        </>
      )}
    </div>
  );
}
