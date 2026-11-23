// Letters NFD does not split into a base letter and an accent. Mirrors
// _ASCII_FOLD in tools/pro_profiles/doubles_load.py (plus å, which NFD folds anyway).
const ASCII_FOLD: Record<string, string> = {
  ø: "o",
  æ: "ae",
  å: "a",
  ß: "ss",
  đ: "d",
  ł: "l",
  œ: "oe",
};

/** Lowercase and strip accents so "Antonsen" matches "Ántonsen" and "boje" matches "Bøje". */
export function normalizeName(s: string): string {
  return s
    .toLowerCase()
    .replace(/[øæåßđłœ]/g, (c) => ASCII_FOLD[c])
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/\s+/g, " ");
}

export const matchCount = (n: number) => `${n} ${n === 1 ? "match" : "matches"}`;
