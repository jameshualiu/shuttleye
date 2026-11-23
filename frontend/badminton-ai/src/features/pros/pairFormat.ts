import type { PairEvent, PairIndexPlayer, PairMeasureKey, PairView, Share } from "./types";

// Display helpers for the doubles pages. They format JSON values; no statistics here.

export const eventLabels: Record<PairEvent, string> = {
  MD: "Men's doubles",
  WD: "Women's doubles",
  XD: "Mixed doubles",
};

/** "Baek Ha Na / Lee So Hee", from the players' display names. */
export const pairName = (players: readonly PairIndexPlayer[]) =>
  players.map((p) => p.name).join(" / ");

/** "Korea", or "Malaysia / Indonesia" when the partners differ. */
export function nationalities(players: readonly PairIndexPlayer[]): string {
  const [a, b] = players;
  return a.nationality === b.nationality ? a.nationality : `${a.nationality} / ${b.nationality}`;
}

/** Whole percent for display. Callers handle null. */
export const pct = (value: number) => `${Math.round(value)}%`;

export const isShown = (value: Share): value is number => value !== null;

export function ordinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

export const count = (n: number, one: string, many: string) =>
  `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;

/** Typical pair value and (all-matches view of a ranked pair only) rank for a measure. */
export const compare = (view: PairView, key: PairMeasureKey) => ({
  typical: view.typical[key],
  rank: view.ranks[key],
});
