import type { GameScore } from "./types";

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
