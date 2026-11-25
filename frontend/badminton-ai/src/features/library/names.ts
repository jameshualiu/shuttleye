import type { GameScore } from "./types";

/**
 * Short name for tight spaces. BWF names carry the family name in capitals
 * ("Viktor AXELSEN", "LEE Zii Jia"); use that word, title-cased. Otherwise the last word.
 */
export function surname(name: string): string {
  const words = name.trim().split(/\s+/);
  const caps = words.find((w) => w.length > 1 && w === w.toUpperCase() && /[A-Z]/.test(w));
  const word = caps ?? words[words.length - 1] ?? name;
  return word.charAt(0) + word.slice(1).toLowerCase();
}

/** "yonex-thailand-open-2021" -> "Yonex Thailand Open 2021". */
export function editionName(editionId: string): string {
  return editionId
    .split("-")
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export function scoreText(score: [number, number] | GameScore | null): string {
  if (!score) return "–";
  const [a, b] = Array.isArray(score) ? score : [score.a, score.b];
  return `${a}–${b}`;
}
