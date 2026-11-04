"use client";

import { CalendarPlus, Loader2, Scale } from "lucide-react";
import { useState } from "react";

import { addCalendarEvent, assessBail } from "@/lib/api-advocate";
import { bailRequest, EMPTY_BAIL_FORM, formatDate, routeStatusMeta, type BailForm } from "@/lib/advocate-presentation";
import type { BailAssessment, BailDate, BailRouteFinding, BailRouteKey } from "@/lib/types-advocate";
import { Badge, Bullets, CoverageBanner, DateField, ErrorLine, errorText, SourceList, TriSelect } from "./shared";

const ROUTES: { key: BailRouteKey; label: string }[] = [
  { key: "regular", label: "Regular" },
  { key: "anticipatory", label: "Anticipatory" },
  { key: "default", label: "Default" },
  { key: "undertrial", label: "Undertrial (s.479)" },
];

function RouteCard({ route, caseId }: { route: BailRouteFinding; caseId?: string }) {
  const meta = routeStatusMeta(route.status);
  const [added, setAdded] = useState<Record<string, boolean>>({});
  const [failure, setFailure] = useState("");
  const add = async (row: BailDate) => {
    if (!caseId) return;
    setFailure("");
    try {
      await addCalendarEvent(caseId, {
        kind: "limitation",
        title: `${route.label}: ${row.label}`,
        due_on: row.date,
        basis: { provision: row.provision, computed_from: row.computed_from, computed: true },
      });
      setAdded((current) => ({ ...current, [row.label]: true }));
    } catch (error) {
      setFailure(errorText(error));
    }
  };
  return (
    <article className="adv-card">
      <div className="adv-card-head">
        <h4>{route.label}</h4>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>
      <p>{route.headline}</p>
      {route.forum && <p className="adv-meta">Forum: {route.forum}</p>}
      {!!route.dates.length && (
        <ul className="adv-dates">
          {route.dates.map((row) => (
            <li key={row.label} className="adv-date">
              <span className="adv-grow">
                <strong>{formatDate(row.date)}</strong> <span className="adv-meta">{row.label}</span>
                <span className="adv-meta" style={{ display: "block" }}>{row.computed_from}, {row.provision}</span>
              </span>
              <Badge tone={row.state === "passed" ? "warn" : "neutral"}>{row.state === "passed" ? "Passed" : row.state === "today" ? "Today" : "Upcoming"}</Badge>
              {caseId && (
                <button type="button" className="draft-action" disabled={added[row.label]} onClick={() => void add(row)}>
                  <CalendarPlus size={13} />{added[row.label] ? "Added" : "Add to calendar"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <Bullets title="Not recorded" items={route.missing} />
      <Bullets title="Keep in view" items={route.cautions} />
      <div>
        <p className="adv-subhead">Provisions, as they read</p>
        <SourceList sources={route.sources} />
      </div>
      <ErrorLine text={failure} />
    </article>
  );
}

export function BailAssessmentView({ result, caseId }: { result: BailAssessment; caseId?: string }) {
  return (
    <div className="adv-section">
      <p className="adv-lede">Assessed as of {formatDate(result.as_of)}. {result.method}</p>
      {result.pre_bnss_notice && (
        <div className="adv-notice is-bad" role="note">
          <strong>This may be governed by the repealed Code.</strong>
          <span>{result.pre_bnss_notice.text}</span>
          {result.pre_bnss_notice.counterparts.map((item) => (
            <span key={`${item.route}-${item.repealed_provision}`}>{item.bnss_provision} corresponds to {item.repealed_provision}{item.elements_changed ? ", and the concordance marks it as changed" : ""}.</span>
          ))}
          <SourceList sources={result.pre_bnss_notice.sources} />
        </div>
      )}
      <div className="adv-list">{result.routes.map((route) => <RouteCard key={route.route} route={route} caseId={caseId} />)}</div>
      <div className="adv-section">
        <h4 className="adv-heading">Passages in the judgments held</h4>
        <CoverageBanner coverage={result.coverage} />
        {result.authorities_note && <p className="adv-meta">{result.authorities_note}</p>}
        <ul className="adv-list">
          {result.authorities.map(({ source, holding_language }) => (
            <li key={source.chunk_id} className="adv-card">
              <p className="adv-meta">{source.title}{source.court ? `, ${source.court}` : ""}{source.decision_year ? `, ${source.decision_year}` : ""}</p>
              {holding_language.map((line) => <blockquote key={line} className="adv-passage">{line}</blockquote>)}
              <SourceList sources={[source]} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function BailTool({ caseId }: { caseId: string }) {
  const [form, setForm] = useState<BailForm>(EMPTY_BAIL_FORM);
  const [save, setSave] = useState(true);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [result, setResult] = useState<BailAssessment | null>(null);
  const set = <K extends keyof BailForm>(key: K) => (value: BailForm[K]) => setForm((current) => ({ ...current, [key]: value }));
  const toggleRoute = (route: BailRouteKey) =>
    setForm((current) => ({
      ...current,
      routes: current.routes.includes(route) ? current.routes.filter((item) => item !== route) : [...current.routes, route],
    }));
  const run = async () => {
    setBusy(true);
    setFailure("");
    try {
      setResult(await assessBail(caseId, bailRequest(form, save)));
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="adv-section">
      <p className="adv-lede">
        Enter what you know. Dates are computed from the text of the BNSS with no model involved, and a fact
        left as &ldquo;not recorded&rdquo; is reported as missing rather than assumed. It reads the section on those facts; it
        does not say what a court will do.
      </p>
      <form className="adv-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <fieldset className="adv-fieldset">
          <legend>Routes to assess</legend>
          <div className="adv-checks">
            {ROUTES.map((route) => (
              <label key={route.key} className="adv-check">
                <input type="checkbox" checked={form.routes.includes(route.key)} onChange={() => toggleRoute(route.key)} />
                {route.label}
              </label>
            ))}
          </div>
          <small className="adv-meta">Leave all clear to assess all four.</small>
        </fieldset>
        <fieldset className="adv-fieldset">
          <legend>The offence</legend>
          <div className="adv-grid">
            <label className="adv-label">Classification
              <select className="field" value={form.classification} onChange={(event) => set("classification")(event.target.value)}>
                <option value="unknown">Not recorded</option>
                <option value="bailable">Bailable</option>
                <option value="non_bailable">Non-bailable</option>
              </select>
              <small>From the First Schedule or the special Act. It is not inferred.</small>
            </label>
            <label className="adv-label">Maximum punishment, in years
              <input className="field" inputMode="decimal" value={form.maxPunishmentYears} onChange={(event) => set("maxPunishmentYears")(event.target.value)} placeholder="Not recorded" />
              <small>Leave blank for life or death, and answer below.</small>
            </label>
            <TriSelect label="Death or life specified as a punishment?" value={form.punishableWithDeathOrLife} onChange={set("punishableWithDeathOrLife")} />
            <TriSelect label="Accusation under BNS s.65 or s.70(2)?" value={form.involvesBns65Or702} onChange={set("involvesBns65Or702")} hint="s.482(4) excludes anticipatory bail for these." />
            <label className="adv-label" style={{ gridColumn: "1 / -1" }}>The accusation, in a line
              <input className="field" value={form.offenceDescription} onChange={(event) => set("offenceDescription")(event.target.value)} placeholder="Used to find passages in the judgments held. Optional." maxLength={2000} />
            </label>
          </div>
        </fieldset>
        <fieldset className="adv-fieldset">
          <legend>Dates and custody</legend>
          <div className="adv-grid">
            <DateField label="Information recorded" value={form.informationRecordedOn} onChange={set("informationRecordedOn")} hint="A date before 1 July 2024 raises the savings clause." />
            <DateField label="Arrest" value={form.arrestedOn} onChange={set("arrestedOn")} />
            <DateField label="First remand" value={form.firstRemandOn} onChange={set("firstRemandOn")} hint="The s.187(3) period runs from here, not from the arrest." />
            <TriSelect label="Police report filed?" value={form.reportFiled} onChange={set("reportFiled")} />
            <DateField label="Report filed on" value={form.reportFiledOn} onChange={set("reportFiledOn")} />
            <TriSelect label="In custody now?" value={form.inCustody} onChange={set("inCustody")} />
            <DateField label="Detention began" value={form.custodyStartedOn} onChange={set("custodyStartedOn")} hint="For the s.479 fractions." />
            <label className="adv-label">Earlier detention, in days
              <input className="field" inputMode="numeric" value={form.earlierDetentionDays} onChange={(event) => set("earlierDetentionDays")(event.target.value)} placeholder="0" />
            </label>
            <label className="adv-label">Delay caused by the accused, in days
              <input className="field" inputMode="numeric" value={form.delayByAccusedDays} onChange={(event) => set("delayByAccusedDays")(event.target.value)} placeholder="0" />
              <small>Excluded under the Explanation to s.479. The Court decides what counts.</small>
            </label>
          </div>
        </fieldset>
        <fieldset className="adv-fieldset">
          <legend>The accused</legend>
          <div className="adv-grid">
            <TriSelect label="First-time offender?" value={form.firstTimeOffender} onChange={set("firstTimeOffender")} hint="Never convicted of any offence (s.479(1), first proviso)." />
            <TriSelect label="Another offence or case pending?" value={form.otherCasesPending} onChange={set("otherCasesPending")} hint="s.479(2)." />
            <TriSelect label="Previous convictions of the s.480(1)(ii) kind?" value={form.previousConvictionBar} onChange={set("previousConvictionBar")} />
            <TriSelect label="Child, woman, sick or infirm?" value={form.childWomanSickOrInfirm} onChange={set("childWomanSickOrInfirm")} hint="s.480(1), first proviso." />
          </div>
        </fieldset>
        <fieldset className="adv-fieldset">
          <legend>Trial before a Magistrate</legend>
          <div className="adv-grid">
            <TriSelect label="Triable by a Magistrate?" value={form.triableByMagistrate} onChange={set("triableByMagistrate")} />
            <DateField label="First date fixed for evidence" value={form.firstEvidenceDate} onChange={set("firstEvidenceDate")} hint="Starts the sixty days in s.480(6)." />
            <TriSelect label="In custody throughout?" value={form.inCustodyWholeTrial} onChange={set("inCustodyWholeTrial")} />
          </div>
        </fieldset>
        <div className="adv-actions">
          <button type="submit" className="button-primary" disabled={busy}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Scale size={15} />}Assess
          </button>
          <label className="adv-check"><input type="checkbox" checked={save} onChange={(event) => setSave(event.target.checked)} />Keep in this case</label>
        </div>
        <ErrorLine text={failure} />
      </form>
      {result && <BailAssessmentView result={result} caseId={caseId} />}
    </div>
  );
}
