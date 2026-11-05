/**
 * Questions to ask next, chosen by rule with no model. They are only questions:
 * no legal fact is stated here, and none asks how a matter will turn out, because
 * the product does not predict outcomes and must not suggest that it does.
 */
import type { UiKey } from "./citizen-i18n";

export type FollowUpTopic = "procedure" | "offence" | "evidence" | "rights" | "consumer" | "general";

interface CitedProvision {
  act_name?: string | null;
  title?: string;
  section_mappings?: unknown[];
}

// First match wins, most specific first. Names only, the same ones the lookup uses.
const TOPIC_NAMES: [FollowUpTopic, RegExp][] = [
  ["consumer", /consumer protection/i],
  ["evidence", /sakshya adhiniyam|evidence act/i],
  ["procedure", /nagarik suraksha|criminal procedure|civil procedure/i],
  ["offence", /nyaya sanhita|penal code/i],
  ["rights", /constitution of india/i],
];

/** The most cited topic, ties to whichever was cited first. */
export function followUpTopic(citations: CitedProvision[]): FollowUpTopic {
  const counts = new Map<FollowUpTopic, number>();
  for (const citation of citations) {
    const name = `${citation.act_name ?? ""} ${citation.title ?? ""}`;
    const topic = TOPIC_NAMES.find(([, pattern]) => pattern.test(name))?.[0];
    if (topic) counts.set(topic, (counts.get(topic) ?? 0) + 1);
  }
  let best: FollowUpTopic = "general";
  let most = 0;
  counts.forEach((count, topic) => {
    if (count > most) { best = topic; most = count; }
  });
  return best;
}

const CITIZEN: Record<FollowUpTopic, UiKey[]> = {
  procedure: ["fuNextSteps", "fuDocuments", "fuTimeLimits"],
  offence: ["fuWhatMustShow", "fuHowReport", "fuFreeHelp"],
  evidence: ["fuProofKeep", "fuCopies", "fuFreeHelp"],
  rights: ["fuUseRight", "fuComplainWhere", "fuFreeHelp"],
  consumer: ["fuConsumerFile", "fuDocuments", "fuTimeLimits"],
  general: ["fuSimpler", "fuNextSteps", "fuFreeHelp"],
};

// Professional screens are not translated.
const POLICE: Record<FollowUpTopic, string[]> = {
  procedure: ["What time limits apply at this stage?", "What should be recorded for this step?", "Which safeguards apply at this stage?"],
  offence: ["What ingredients does the investigation need to establish?", "What evidence bears on each ingredient?", "Which related provisions should be checked?"],
  evidence: ["How should this evidence be collected and recorded?", "What does the provision require for its proof?", "What should the chain of custody show?"],
  rights: ["What does this require of an officer in practice?", "What should be recorded to show compliance?", "Which judgments explain this requirement?"],
  consumer: ["Which authority deals with this?", "Which related provisions should be checked?", "What should be recorded?"],
  general: ["Which provisions govern this?", "What should be recorded?", "What are the procedural steps?"],
};

const ADVOCATE: Record<FollowUpTopic, string[]> = {
  procedure: ["Which judgments have interpreted this provision?", "What timing requirements apply?", "Is there a contrary line of authority?"],
  offence: ["What are the ingredients, and how have courts read them?", "Which judgments have interpreted this provision?", "Is there a contrary line of authority?"],
  evidence: ["How have courts treated admissibility on this point?", "What foundation has to be laid for this evidence?", "Is there a contrary line of authority?"],
  rights: ["Which judgments set out the test here?", "How has this been applied to similar facts?", "Is there a contrary line of authority?"],
  consumer: ["Which forum has jurisdiction over this?", "What timing requirements apply?", "Which judgments have interpreted this provision?"],
  general: ["Which provisions govern this?", "Which judgments have interpreted this?", "Is there a contrary line of authority?"],
};

const CHANGED_CODE = "What differs between the earlier provision and the current one?";

export const MAX_FOLLOW_UPS = 3;

/** Keys for a citizen, translated where they are shown. */
export function citizenFollowUps(citations: CitedProvision[]): UiKey[] {
  return CITIZEN[followUpTopic(citations)];
}

/** English questions for a police officer or an advocate. */
export function professionalFollowUps(role: string | undefined, citations: CitedProvision[]): string[] {
  const list = (role === "police" ? POLICE : ADVOCATE)[followUpTopic(citations)];
  const renumbered = citations.some((citation) => (citation.section_mappings?.length ?? 0) > 0);
  return (renumbered ? [CHANGED_CODE, ...list] : list).slice(0, MAX_FOLLOW_UPS);
}

/** Everything this file can suggest in English, so a test can read all of it. */
export const ALL_PROFESSIONAL_QUESTIONS: string[] = [
  CHANGED_CODE,
  ...Object.values(POLICE).flat(),
  ...Object.values(ADVOCATE).flat(),
];

/** Filling is an event because the composer keeps its own text and sits far from the answer. */
export const FILL_COMPOSER_EVENT = "corpusil:fill-composer";
