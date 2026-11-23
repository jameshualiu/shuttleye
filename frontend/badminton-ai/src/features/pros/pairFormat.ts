import type { Finding, PairEvent, PairIndexPlayer, PairMeasureKey, PairSampleKey, PairView, Share } from "./types";

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

// What each sample count counts, as [one, many].
const sampleUnits: Record<PairSampleKey, [string, string]> = {
  "serve.short_share": ["serve", "serves"],
  "serve.win_rate": ["rally", "rallies"],
  "serve.third_down": ["third shot", "third shots"],
  "receive.attack_share": ["return", "returns"],
  "receive.win_rate": ["rally", "rallies"],
  "first4.share": ["rally", "rallies"],
  "first4.win_rate": ["rally", "rallies"],
  "rally.attack_share": ["shot", "shots"],
  "rally.formation_attack": ["shot", "shots"],
  "serve.placement": ["serve", "serves"],
  "receive.mix": ["return", "returns"],
  "points.lost": ["point", "points"],
  "points.won": ["point", "points"],
  "mixed.serve_by": ["serve", "serves"],
  "mixed.receive_by": ["return", "returns"],
};

/** The count behind one value, e.g. "22 rallies"; undefined if the JSON has none. */
export function sample(view: PairView, key: PairSampleKey): string | undefined {
  const n = view.samples[key];
  if (n === undefined) return undefined;
  const [one, many] = sampleUnits[key];
  return count(n, one, many);
}

/** Typical pair value, (all-matches view of a ranked pair only) rank and sample count for a measure. */
export const compare = (view: PairView, key: PairMeasureKey) => ({
  typical: view.typical[key],
  rank: view.ranks[key],
  sample: sample(view, key),
});

/** rally.* findings belong to the rest-of-the-rally panel; the rest to serve & receive. */
export const isRallyFinding = (f: Finding) => f.key.startsWith("rally.");
