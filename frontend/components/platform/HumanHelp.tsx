"use client";
import { LifeBuoy, Phone } from "lucide-react";
import { useCitizenLang } from "@/components/citizen/useCitizenLang";
import { humanHelpRoutes, LEGAL_AID_HELPLINE, type HelpRoute } from "@/lib/human-help";

/** Shown with every abstention, so declining never ends the conversation. */
export default function HumanHelp({ role }: { role?: string }) {
  const citizen = (role ?? "citizen") === "citizen";
  const { t } = useCitizenLang(citizen);
  const help = humanHelpRoutes(role ?? "citizen");
  const { heading, lead, routes } = citizen ? {
    heading: t("helpHeading"),
    lead: t("helpLead"),
    routes: [
      { title: t("helpNalsa"), detail: t("helpNalsaDetail"), phone: LEGAL_AID_HELPLINE },
      { title: t("helpDlsa"), detail: t("helpDlsaDetail") },
      { title: t("helpAdvocate"), detail: t("helpAdvocateDetail") },
    ],
  } : help;
  return (
    <aside className="human-help" aria-label={citizen ? t("helpAria") : "Where to get help from a person"}>
      <LifeBuoy size={18} aria-hidden="true" />
      <div>
        <h3>{heading}</h3>
        <p>{lead}</p>
        <ul>
          {routes.map((route: HelpRoute) => (
            <li key={route.title}>
              {route.phone
                ? <a href={`tel:${route.phone}`}><Phone size={13} aria-hidden="true" /><strong>{route.title}</strong></a>
                : <strong>{route.title}</strong>}
              <span>{route.detail}</span>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
