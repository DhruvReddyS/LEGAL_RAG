/**
 * Where a police officer or an advocate is in the app, held in the address bar so
 * back, forward, reload and a shared link all land on the same screen. This is a
 * static export, so the screen is a query parameter and there are no server routes.
 * The address only says what to show: a case still has to be in the signed-in
 * person's own list before anything of it is read.
 */
export type ProSection = "dashboard" | "cases" | "case" | "deadlines" | "drafts" | "research" | "law" | "unit" | "help";

export interface ProRoute {
  section: ProSection;
  caseId?: string;
  tab?: string;
  tool?: string;
}

const SECTIONS: readonly string[] = ["dashboard", "cases", "case", "deadlines", "drafts", "research", "law", "unit", "help"];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SLUG = /^[a-z][a-z-]{0,30}$/;

export function parseProRoute(search: string): ProRoute {
  const params = new URLSearchParams(search);
  const section = params.get("s");
  // The law lookup writes its own ?q= in place, on the public page and here alike.
  if (!section && params.has("q")) return { section: "law" };
  if (!section || !SECTIONS.includes(section)) return { section: "dashboard" };
  if (section !== "case") return { section: section as ProSection };
  const caseId = params.get("case") ?? "";
  if (!UUID.test(caseId)) return { section: "cases" };
  const route: ProRoute = { section: "case", caseId };
  const tab = params.get("tab");
  if (tab && SLUG.test(tab)) {
    route.tab = tab;
    const tool = params.get("tool");
    if (tool && SLUG.test(tool)) route.tool = tool;
  }
  return route;
}

export function proHref(route: ProRoute): string {
  if (route.section === "dashboard") return "/";
  const params = new URLSearchParams({ s: route.section });
  if (route.section === "case" && route.caseId) {
    params.set("case", route.caseId);
    if (route.tab) params.set("tab", route.tab);
    if (route.tab && route.tool) params.set("tool", route.tool);
  }
  return `/?${params.toString()}`;
}

export const sameRoute = (a: ProRoute, b: ProRoute): boolean => proHref(a) === proHref(b);
