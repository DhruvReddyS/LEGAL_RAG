import type { ComponentType } from "react";

import BulkUpload from "@/components/case/BulkUpload";
import CaseNotes from "@/components/case/CaseNotes";

/** The two separately built features a case page plugs in. */
const CaseFilesUpload = ({ caseId, onUploaded }: { caseId: string; onUploaded?: () => void }) => (
  <BulkUpload caseId={caseId} docType="evidence" onIndexed={onUploaded ?? (() => undefined)} />
);

export const CaseBulkUpload: ComponentType<{ caseId: string; onUploaded?: () => void }> | null = CaseFilesUpload;
export const CaseNotesPanel: ComponentType<{ caseId: string }> | null = CaseNotes;
