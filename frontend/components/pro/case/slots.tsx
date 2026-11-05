import type { ComponentType } from "react";

/**
 * The two places a separately built feature plugs into a case page. Each is one
 * line: replace `null` with the import. Nothing else has to change.
 *
 * FILES SLOT: replaces the single-file form at the top of the Files tool.
 *   import BulkUpload from "@/components/case/BulkUpload";
 *   export const CaseBulkUpload: ... = BulkUpload;
 *
 * NOTES SLOT: adds a Notes tab to every case page, for both roles. The tab is left
 * out altogether until this is set, so nobody sees an empty one.
 *   import CaseNotes from "@/components/case/CaseNotes";
 *   export const CaseNotesPanel: ... = CaseNotes;
 *
 * Both are mounted under a key of the case id with `caseId` as a prop, so nothing
 * from one case can stand under another.
 */
export const CaseBulkUpload: ComponentType<{ caseId: string; onUploaded?: () => void }> | null = null;
export const CaseNotesPanel: ComponentType<{ caseId: string }> | null = null;
