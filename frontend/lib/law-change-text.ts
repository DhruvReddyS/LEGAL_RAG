/** What changed, in a sentence. Every fact comes from the notice, which came from the curated table. */
export function describeLawChange(notice: {
  current_status: string;
  superseded_by: string | null;
  effective: string | null;
}): string {
  if (notice.current_status !== "superseded") {
    return "It was recorded as replaced when you asked. That record has been corrected.";
  }
  const replaced = notice.superseded_by ? `It has been replaced by ${notice.superseded_by}` : "It is now recorded as replaced";
  return notice.effective ? `${replaced}, effective ${notice.effective}.` : `${replaced}.`;
}
