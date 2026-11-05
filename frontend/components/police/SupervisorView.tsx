"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { errorText, ErrorNote, Loading, Pill } from "@/components/police/shared";
import { getMyUnits, getSupervisedUnit } from "@/lib/api-police";
import { formatMoment, registerWords, sumCounts, supervisedUnits, timeLeft } from "@/lib/police-presentation";
import type { MyUnit, SupervisedUnit } from "@/lib/types-police";

function UnitPanel({ unitId }: { unitId: string }) {
  const [data, setData] = useState<SupervisedUnit | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const load = useCallback(async () => {
    setError("");
    try { setData(await getSupervisedUnit(unitId)); setNow(Date.now()); }
    catch (cause) { setData(null); setError(errorText(cause)); }
  }, [unitId]);
  useEffect(() => { void load(); }, [load]);

  if (error) return <ErrorNote message={error} />;
  if (!data) return <Loading label="Reading the unit…" />;
  const urgent = sumCounts(data.counts, ["overdue", "imminent"]);
  return (
    <div className="police-stack">
      <div className="police-counts" aria-label={`${data.unit_name} at a glance`}>
        <div className={`police-count ${urgent ? "is-bad" : "is-zero"}`}><strong>{urgent}</strong><span>Overdue or expiring within {data.imminent_hours} hours</span></div>
        <div className={`police-count ${data.counts.breached ? "is-bad" : "is-zero"}`}><strong>{data.counts.breached ?? 0}</strong><span>Breached on record</span></div>
        <div className={`police-count ${data.counts.unknown ? "is-warn" : "is-zero"}`}><strong>{data.counts.unknown ?? 0}</strong><span>Deadlines that cannot be determined</span></div>
        <div className={`police-count ${data.compliance.not_satisfied ? "is-bad" : "is-zero"}`}><strong>{data.compliance.not_satisfied ?? 0}</strong><span>Duties recorded as not done</span></div>
        <div className="police-count"><strong>{data.compliance.satisfied ?? 0}</strong><span>Duties recorded as done</span></div>
        <div className={`police-count ${data.compliance.not_recorded ? "is-warn" : "is-zero"}`}><strong>{data.compliance.not_recorded ?? 0}</strong><span>Duties nobody has recorded</span></div>
      </div>
      <div className="police-row-actions">
        <span className="police-note">{data.officer_count} officer{data.officer_count === 1 ? "" : "s"}, {data.cases.length} open case{data.cases.length === 1 ? "" : "s"}. Read {formatMoment(data.evaluated_at)}.</span>
        <button type="button" className="police-mini" onClick={() => void load()}><RefreshCw size={13} aria-hidden="true" />Refresh</button>
      </div>
      {!data.cases.length && <p className="police-empty">No open case in this unit.</p>}
      <ul className="grid gap-3">
        {data.cases.map((item) => (
          <li key={item.case_id} className="police-card">
            <div className="police-card-head">
              <h4>{item.title}<small>{item.officer_name}{!item.has_facts ? ". No dates recorded, so nothing can be computed." : ""}</small></h4>
              {sumCounts(item.counts, ["overdue", "imminent"]) > 0 && <Pill words={{ label: `${sumCounts(item.counts, ["overdue", "imminent"])} ${sumCounts(item.counts, ["overdue", "imminent"]) === 1 ? "needs" : "need"} attention`, tone: "bad" }} />}
            </div>
            <dl className="police-facts">
              <div><dt>Breached</dt><dd>{item.counts.breached ?? 0}</dd></div>
              <div><dt>Cannot be determined</dt><dd>{item.counts.unknown ?? 0}</dd></div>
              <div><dt>Duties done</dt><dd>{item.compliance.satisfied ?? 0}</dd></div>
              <div><dt>Duties not done</dt><dd>{item.compliance.not_satisfied ?? 0}</dd></div>
              <div><dt>Duties not recorded</dt><dd>{item.compliance.not_recorded ?? 0}</dd></div>
            </dl>
            {item.attention.length > 0 && (
              <ul className="police-checks">
                {item.attention.map((row) => (
                  <li key={row.key} className="police-check-row">
                    <div className="police-check-row-top">
                      <p>{row.obligation}</p>
                      <Pill words={registerWords(row)} />
                    </div>
                    <small>
                      <span className="provision-tag">{row.provision}</span>{" "}
                      {row.due_at ? `${formatMoment(row.due_at)} (${timeLeft(row.due_at, now)})` : row.state_reason}
                    </small>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SupervisorView({ units }: { units: MyUnit[] | null }) {
  const mine = supervisedUnits(units ?? []);
  const [chosen, setChosen] = useState("");
  // The units arrive after this mounts, on a reload or a shared link, so which one is
  // open is worked out on each render rather than fixed at the first, empty one.
  const unitId = mine.some((unit) => unit.unit_id === chosen) ? chosen : mine[0]?.unit_id ?? "";
  if (!units) return <Loading label="Reading your units…" />;
  if (!mine.length) return <p className="police-empty">You do not supervise a unit. An administrator grants this.</p>;
  return (
    <div className="police-stack">
      <p className="police-note">
        Counts and deadline states for the open cases of officers in your unit. Evidence, witnesses, statements and drafts stay with each officer, and being a supervisor opens none of their case pages. Each time you open this, it is logged, and each officer can see that you looked.
      </p>
      {mine.length > 1 && (
        <div className="police-tabs" role="tablist" aria-label="Units you supervise">
          {mine.map((unit) => (
            <button key={unit.unit_id} type="button" role="tab" aria-selected={unit.unit_id === unitId} onClick={() => setChosen(unit.unit_id)}>{unit.unit_name}</button>
          ))}
        </div>
      )}
      <UnitPanel key={unitId} unitId={unitId} />
    </div>
  );
}

/** Null until read, so a supervisor is not told they supervise nothing while it loads. */
export function useMyUnits(enabled: boolean): MyUnit[] | null {
  const [units, setUnits] = useState<MyUnit[] | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    getMyUnits().then((rows) => { if (!cancelled) setUnits(rows); }).catch(() => { if (!cancelled) setUnits([]); });
    return () => { cancelled = true; };
  }, [enabled]);
  return units;
}
