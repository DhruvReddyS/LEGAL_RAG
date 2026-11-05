/** Which side of a comparison a citation sits on. Pure, so it can be tested alone. */

// The codes the concordance maps to. Read from the mapping's own direction, not
// from any judgment about which text matters more.
const REPLACING_CODES = new Set(["BNS", "BNSS", "BSA"]);

export interface ComparisonPair<T> {
  earlier: T;
  later: T;
}

/** The earlier code goes first, whichever one the reader happened to open. */
export function arrangeComparison<T>(openedCode: string, opened: T, counterpart: T): ComparisonPair<T> {
  return REPLACING_CODES.has(openedCode)
    ? { earlier: counterpart, later: opened }
    : { earlier: opened, later: counterpart };
}
