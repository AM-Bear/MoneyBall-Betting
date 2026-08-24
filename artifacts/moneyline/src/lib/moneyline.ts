/** American moneyline parsing, shared by the Edge Finder and the GameCard
 *  verdict slot.
 *
 *  One definition, so the two surfaces cannot drift on what counts as a
 *  usable price. A valid American line is a whole number with |x| >= 100 and
 *  x != 0 — the same rule the backend validator enforces, so a line that
 *  parses here is a line the API will accept.
 */

export function parseMoneyline(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed || !/^[+-]?\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

export function isMalformedMoneyline(value: string): boolean {
  if (!value.trim()) return false;
  const parsed = parseMoneyline(value);
  return parsed === null || parsed === 0 || Math.abs(parsed) < 100;
}

/** The parsed line when the text is a usable American price, else null.
 *  Callers send this straight to the API: a half-typed or malformed entry
 *  becomes an absent price, never a guessed one. */
export function validMoneyline(value: string): number | null {
  const parsed = parseMoneyline(value);
  if (parsed === null || parsed === 0 || Math.abs(parsed) < 100) return null;
  return parsed;
}
