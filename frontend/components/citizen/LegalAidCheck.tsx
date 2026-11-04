"use client";
import { useState } from "react";
import { AID_CATEGORIES, AID_TEXT, checkLegalAid } from "@/lib/citizen-law/legal-aid";
import { Cites, Disclaimer, HumanRoute } from "./shared";
import { useCitizenLang } from "./useCitizenLang";

export default function LegalAidCheck() {
  const { lang, t } = useCitizenLang();
  const [selected, setSelected] = useState<string[]>([]);
  const result = checkLegalAid(selected);
  return <div className="ctz-aid">
    <p className="ctz-lead">{t("aidLead")}</p>
    <fieldset className="ctz-checks">
      <legend className="sr-only">{t("toolLegalAid")}</legend>
      {AID_CATEGORIES.map(category => <label key={category.id} className="ctz-check">
        <input type="checkbox" checked={selected.includes(category.id)} onChange={event => setSelected(current => event.target.checked ? [...current, category.id] : current.filter(id => id !== category.id))}/>
        <span>{category.label[lang]}</span>
      </label>)}
    </fieldset>
    <section className="ctz-block" aria-live="polite">
      {result.status === "none_selected" && <p>{AID_TEXT.noneSelected[lang]}</p>}
      {result.status === "income_only" && <><p>{AID_TEXT.incomeOnly[lang]}</p><Cites ids={result.cites}/></>}
      {result.status === "may_qualify" && <><p>{AID_TEXT.mayQualify[lang]}</p>{selected.includes("income") && <p>{AID_TEXT.incomeOnly[lang]}</p>}<Cites ids={[...result.cites, ...(selected.includes("income") ? ["lsa-13-2"] : [])]}/></>}
    </section>
    <section className="ctz-block"><h3>{t("aidHowToReach")}</h3><p>{AID_TEXT.reach[lang]}</p><p className="ctz-note">{AID_TEXT.take[lang]}</p><Cites ids={["nalsa-15100"]}/></section>
    <HumanRoute/>
    <Disclaimer/>
  </div>;
}
