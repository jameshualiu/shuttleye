/** Lowercase and strip accents so "Antonsen" matches "Ántonsen". */
export function normalizeName(s: string): string {
  return s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().replace(/\s+/g, " ");
}

export const matchCount = (n: number) => `${n} ${n === 1 ? "match" : "matches"}`;
