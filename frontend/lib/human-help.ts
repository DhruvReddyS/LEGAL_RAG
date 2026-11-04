/**
 * Where to turn when the system declines to answer.
 *
 * Refusing is the right behaviour and it is not enough on its own: the person
 * still has the problem. So every abstention names a human route. Routes to
 * institutions only, never to a named advocate: recommending one lawyer would be
 * soliciting on their behalf, which Bar Council rules restrict.
 *
 * The eligibility line is from s.12 of the Legal Services Authorities Act, 1987,
 * as held in the corpus. The helpline is the one citizen_safety.py already uses.
 */

export const LEGAL_AID_HELPLINE = "15100";

export const LEGAL_AID_ELIGIBILITY =
  "Under section 12 of the Legal Services Authorities Act, 1987, free legal services are available to women and children, members of a Scheduled Caste or Scheduled Tribe, people with disabilities, industrial workers, people in custody, victims of trafficking or of a disaster, and people below the income limit their State sets.";

export interface HelpRoute {
  title: string;
  detail: string;
  /** A tel: link where one number reaches it. */
  phone?: string;
}

export function humanHelpRoutes(role: string): { heading: string; lead: string; routes: HelpRoute[] } {
  if (role === "police") {
    return {
      heading: "Take this to someone who can answer it",
      lead: "The corpus could not support an answer. Do not act on a gap. Raise it through your chain of command.",
      routes: [
        { title: "Your legal officer or the public prosecutor", detail: "The route for a question of procedure on a live investigation." },
        { title: "Your supervising officer", detail: "Where the question affects a statutory deadline or a safeguard." },
      ],
    };
  }
  if (role === "advocate") {
    return {
      heading: "This needs research beyond this corpus",
      lead: "The corpus could not support an answer, which is not the same as there being no authority. Coverage of judgments is thin.",
      routes: [
        { title: "A reporter or case-law database", detail: "This corpus holds few judgments, so absence here says little about the law." },
        { title: "A senior or specialist colleague", detail: "Where the point needs judgment on your facts." },
      ],
    };
  }
  return {
    heading: "You can still get help from a person",
    lead: "This system could not find enough support to answer safely. A lawyer or a legal aid office can look at your actual situation.",
    routes: [
      {
        title: `National Legal Services Authority helpline: ${LEGAL_AID_HELPLINE}`,
        detail: "Free legal aid, for those who qualify. Ask them whether you do.",
        phone: LEGAL_AID_HELPLINE,
      },
      {
        title: "District Legal Services Authority",
        detail: "Works from your district court complex and can assign a lawyer without charge.",
      },
      {
        title: "An advocate of your choice",
        detail: "The Bar Association at your district court can tell you how to find one. Ask about fees before you begin.",
      },
    ],
  };
}
