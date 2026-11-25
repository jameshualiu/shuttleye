// Mirror of the Firestore match-library contract (data-flow.md section 8).
// Producer: tools/library. Keep names identical.
import type { Clip, Finding, Photo, PlayerFilter, PlayerContext, ProEvent, ViewKind } from "../pros/types";

export type { Clip, Finding };

export type Side = "A" | "B";
export type MatchStatus = "unpublished" | "published";

export type LibraryPlayerRef = { id: string; name: string; event: ProEvent };
export type GameScore = { a: number; b: number };

export type ShotDoc = {
  t: number;
  p: Side | null;
  g: string | null;
  d: string | null;
  z: string | null;
  s: boolean;
};

export type RallyDoc = {
  n: number;
  set: number;
  startSec: number;
  endSec: number;
  /** [A, B] before the rally; null once an earlier rally of the set had no read score. */
  scoreBefore: [number, number] | null;
  winner: Side | null;
  shots: ShotDoc[];
};

// Shares are percentages to one decimal; null below the minimum sample.
export type Share = number | null;
export type ShareMap = Record<string, number | null>;

export type Insights = {
  phaseMix: Record<"start" | "mid" | "late", ShareMap>;
  replies: Record<string, ShareMap>;
  zones: ShareMap;
  tempo: { secPerShot: number | null; rallyShots: number | null };
  bands: { band: "short" | "mid" | "long"; label: string; rallies: number; winRate: Share }[];
  serve: {
    serves: number;
    shortShare: Share;
    pointsWonShort: Share;
    pointsWonLong: Share;
  };
  smashWins: { smashes: number; winShare: Share };
};

export type PlayerInsights = { insights: Insights; findings: Finding[] };
export type MatchInsights = Record<Side, PlayerInsights>;

export type MatchDoc = {
  id: string;
  youtubeId: string;
  editionId: string;
  round: string;
  date: string;
  players: Record<Side, LibraryPlayerRef>;
  winner: Side;
  games: GameScore[] | null;
  attributed: boolean;
  status: MatchStatus;
  analyzer: {
    models: Record<string, unknown>;
    warnings: string[];
    skippedSteps: string[];
    timings: Record<string, Record<string, number>>;
  };
  accuracy: { hitF1: number | null; side: number | null; type6: number | null; ten: number | null } | null;
  summary: { rallies: number; avgShots: number; durationSec: number };
  rallies: RallyDoc[];
  insights: MatchInsights | null;
};

export type LibraryIndexPlayer = {
  id: string;
  name: string;
  event: ProEvent;
  matches: number;
  ranked: boolean;
  photo: Photo | null;
};

export type LibraryIndexEdition = { id: string; name: string; season: number; matches: number };

export type LibraryIndexMatch = {
  id: string;
  editionId: string;
  round: string;
  date: string;
  players: Record<Side, LibraryPlayerRef>;
  games: GameScore[] | null;
  youtubeId: string;
};

export type LibraryIndex = {
  players: LibraryIndexPlayer[];
  editions: LibraryIndexEdition[];
  matches: LibraryIndexMatch[];
};

/** players/{id} */
export type LibraryPlayer = {
  id: string;
  name: string;
  event: ProEvent;
  context: PlayerContext;
  summary: string | null;
  photo: Photo | null;
  filters: PlayerFilter[];
};

/** players/{id}/views/{filterId} */
export type LibraryView = {
  kind: ViewKind;
  shots: number;
  rallies: number;
  insights: Insights;
  findings: Finding[];
  rallyBrowser: Clip[];
};

/** Light row for the admin list of unpublished matches. */
export type UnpublishedMatch = {
  id: string;
  players: Record<Side, LibraryPlayerRef>;
  editionId: string;
  round: string;
  date: string;
  games: GameScore[] | null;
  warnings: number;
};
