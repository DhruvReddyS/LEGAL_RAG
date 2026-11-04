import { LifeBuoy, Phone } from "lucide-react";
import { humanHelpRoutes } from "@/lib/human-help";

/** Shown with every abstention, so declining never ends the conversation. */
export default function HumanHelp({ role }: { role?: string }) {
  const { heading, lead, routes } = humanHelpRoutes(role ?? "citizen");
  return (
    <aside className="human-help" aria-label="Where to get help from a person">
      <LifeBuoy size={18} aria-hidden="true" />
      <div>
        <h3>{heading}</h3>
        <p>{lead}</p>
        <ul>
          {routes.map(route => (
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
