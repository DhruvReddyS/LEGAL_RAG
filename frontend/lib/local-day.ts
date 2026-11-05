/**
 * Today's date in the reader's own time, as a date input wants it. toISOString() gives
 * UTC, so in India it still says yesterday until half past five in the morning.
 */
export function localDay(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
