import { Phone } from "lucide-react";
import type { HelplineContact } from "@/lib/types";

export function HelplineNotice({ contacts }: { contacts: HelplineContact[] }) {
  return <aside className="helpline-notice" role="status" aria-label="Helplines">
    <p><strong>If you or someone near you is not safe right now, please call for help.</strong> Your answer is still on its way below.</p>
    <ul>{contacts.map(item => <li key={item.number}><a href={`tel:${item.number}`}><Phone size={13} aria-hidden="true"/>{item.label}: <strong>{item.number}</strong></a></li>)}</ul>
  </aside>;
}
