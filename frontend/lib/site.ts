/**
 * Where the public pages point.
 *
 * APP_HREF is the one place the public site names the application's route. When
 * the app moves off `/` so the landing page can own it, this line changes and
 * nothing else does.
 */
export const APP_HREF = "/?signin=1";

export const SITE_ROUTES = {
  welcome: "/welcome",
  install: "/install",
  privacy: "/privacy",
  terms: "/terms",
  help: "/help",
} as const;

export const SITE_NAV: ReadonlyArray<{ href: string; label: string }> = [
  { href: SITE_ROUTES.install, label: "Install" },
  { href: SITE_ROUTES.help, label: "Help" },
  { href: SITE_ROUTES.privacy, label: "Privacy" },
  { href: SITE_ROUTES.terms, label: "Terms" },
];

export const RELEASES_URL = "https://github.com/DhruvReddyS/LEGAL_RAG/releases";
export const SOURCE_URL = "https://github.com/DhruvReddyS/LEGAL_RAG";

/**
 * Counted from data/legal_kb/metadata/canonical_documents.jsonl on 4 November
 * 2026, one row per canonical document. Not read from the docs, which lag it.
 * A corpus rebuild changes these: recount, and change them with the date.
 */
export const CORPUS_FACTS = {
  countedOn: "5 November 2026",
  documents: 1593,
  central: 1290,
  andhraPradesh: 285,
  telangana: 18,
  judgments: 93,
  supremeCourtJudgments: 79,
  andhraHighCourtJudgments: 14,
  acts: 807,
  rules: 361,
  pages: 56290,
} as const;

/** What an install needs. Measured figures from docs/04-OPERATIONS.md §1. */
export const REQUIREMENTS = {
  memoryGb: 24,
  modelTag: "qwen3:14b",
  modelDownloadGb: 9,
  modelResidentGb: 11.7,
  corpusPdfGb: 3.4,
  corpusAllGb: 14,
} as const;
