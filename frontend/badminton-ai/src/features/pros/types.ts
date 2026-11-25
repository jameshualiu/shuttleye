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

// Doubles pair JSON contract (data-flow.md section 6).
// Producer: tools/pro_profiles/doubles_build.py. Keep names identical.

export type PairEvent = "MD" | "WD" | "XD";

export type PairIndexEntry = {
  id: string;
  event: PairEvent;
  players: [PairIndexPlayer, PairIndexPlayer];
  matches: number;
  ranked: boolean;
};

export type PairIndexPlayer = { id: string; name: string; nationality: string };

export type PairIndex = { pairs: PairIndexEntry[] };

export type PairPlayer = PairIndexPlayer & { gender: string };

export type PairMeasureKey =
  | "serve.short_share"
  | "serve.win_rate"
  | "serve.third_down"
  | "receive.attack_share"
  | "receive.win_rate"
  | "first4.share"
  | "first4.win_rate"
  | "rally.attack_share"
  | "rally.formation_attack";

// Shares are 0-100. null means under the minimum sample (30 serves, returns or rallies).
export type Share = number | null;

/** Keys of PairView.samples: every measure, the display distributions and (XD only) the mixed splits. */
export type PairSampleKey =
  | PairMeasureKey
  | "serve.placement"
  | "receive.mix"
  | "points.lost"
  | "points.won"
  | "mixed.serve_by"
  | "mixed.receive_by";

export type PairView = {
  kind: ViewKind;
  rallies: number;
  serve: {
    shortShare: Share;
    winRate: Share;
    thirdDown: Share;
    placement: { centre: Share; middle: Share; wide: Share; backCentre: Share; backWide: Share };
    serves: number;
  };
  receive: {
    attackShare: Share;
    winRate: Share;
    mix: Record<string, Share>;
    returns: number;
  };
  first4: { share: Share; winRate: Share };
  mixed: {
    serveBy: { man: Share; woman: Share };
    receiveBy: { man: Share; woman: Share };
  } | null;
  rest: {
    attackShare: Share;
    formationAttack: Share;
    roles: { playerId: string; smashShare: Share; netShare: Share }[];
    pointsLost: Record<string, Share>;
    pointsWon: { winner: Share; oppError: Share };
  };
  ranks: Partial<Record<PairMeasureKey, { rank: number; of: number; typical: number }>>;
  /** The count behind each value: serves, returns, rallies or shots. mixed.* only for XD. */
  samples: Partial<Record<PairSampleKey, number>>;
  typical: Partial<Record<PairMeasureKey, number>>;
  findings: Finding[]; // clips are always [] for doubles
};

export type PairProfile = {
  id: string;
  event: PairEvent;
  players: [PairPlayer, PairPlayer];
  context: PlayerContext;
  ranked: boolean;
  summary: string | null;
  filters: PlayerFilter[];
  views: Record<string, PairView>;
};

export type DoublesTournamentEdition = {
  id: string;
  name: string;
  season: number;
  doublesMatches: number;
};

export type DoublesTournamentIndex = { editions: DoublesTournamentEdition[] };

export type PairRef = { id: string; names: string };

export type DoublesTournamentMatch = {
  id: string;
  event: PairEvent;
  round: string;
  date: string;
  winner: PairRef;
  loser: PairRef;
  games: [number, number][];
  incomplete: number[];
};

export type DoublesTournament = {
  id: string;
  name: string;
  season: number;
  matches: DoublesTournamentMatch[];
  pairs: { id: string; event: PairEvent; names: string }[];
};
