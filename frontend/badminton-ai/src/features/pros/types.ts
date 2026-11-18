// Mirror of the pro profile JSON contract (data-flow.md section 5).
// Producer: tools/pro_profiles/build.py. Keep names identical.

export type ProEvent = "MS" | "WS";

export type Photo = {
  src: string;
  credit: string;
  sourceUrl: string;
  focusX: number; // 0-100
  focusY: number; // 0-100
};

export type PlayerIndexEntry = {
  id: string;
  name: string;
  event: ProEvent;
  matches: number;
  ranked: boolean;
  photo: Photo | null;
};

export type PlayerIndex = {
  generatedFrom: string;
  players: PlayerIndexEntry[];
};

export type Clip = {
  youtubeId: string;
  startSec: number;
  endSec: number;
  matchLabel: string;
  scoreLabel: string;
};

export type ShotRow = {
  group: string;
  share: number;
  count: number;
  rank: number | null;
  of: number | null;
  typical: number;
};

export type BandName = "short" | "mid" | "long";

export type BandRow = {
  band: BandName;
  label: string;
  rallies: number;
  winRate: number | null; // null under 30 rallies
  typical: number;
};

export type FindingKind = "style" | "strength" | "weakness";

export type Finding = {
  key: string;
  kind: FindingKind;
  claim: string;
  figure: string;
  comparison: string;
  tip: string | null;
  clips: Clip[];
};

export type ViewKind = "all" | "tournament" | "match";

export type View = {
  kind: ViewKind;
  shots: number;
  rallies: number;
  shotChoice: ShotRow[];
  bands: BandRow[];
  findings: Finding[]; // non-empty only in the "all" view
  // Filtered views: the selection's rallies. "all" view: up to 5 example
  // rallies when there are no findings, otherwise empty.
  rallyBrowser: Clip[];
};

export type PlayerFilter = {
  id: string; // "all" | "t:<edition_id>" | "m:<match_id>"
  label: string;
  kind: ViewKind;
  matches: number;
};

export type PlayerContext = {
  matches: number;
  firstYear: number;
  lastYear: number;
  comparedWith: number;
};

export type PlayerProfile = {
  id: string;
  name: string;
  event: ProEvent;
  context: PlayerContext;
  summary: string | null;
  photo: Photo | null;
  filters: PlayerFilter[];
  views: Record<string, View>;
};

export type TournamentEdition = {
  id: string;
  name: string;
  season: number;
  matches: number;
};

export type TournamentIndex = {
  editions: TournamentEdition[];
};

export type PlayerRef = { id: string; name: string };

export type TournamentMatch = {
  id: string;
  round: string;
  date: string;
  winner: PlayerRef;
  loser: PlayerRef;
  games: [number, number][]; // max recorded score per set, winner first
  incomplete: number[]; // 0-based indexes into games whose score isn't a finished game
};

export type Tournament = {
  id: string;
  name: string;
  season: number;
  matches: TournamentMatch[];
  players: { id: string; name: string; event: ProEvent }[];
};
