import { useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { MotionConfig, motion } from "motion/react";
import { ChevronRight, Moon, Sun } from "lucide-react";
import { useAuthUser } from "../auth/hooks/useAuthUser";
import { useTheme } from "../context/useTheme";

// ── Illustrated panels ────────────────────────────────────────────────────────

function WindowChrome({ title, right }: { title: string; right?: React.ReactNode }) {
    return (
        <div className="flex items-center gap-1.5 px-3 py-2.5 bg-white/[0.03] border-b border-border text-[11px] text-muted-foreground">
            <span className="w-2 h-2 rounded-full bg-[#ff5f56]" />
            <span className="w-2 h-2 rounded-full bg-[#ffbd2e]" />
            <span className="w-2 h-2 rounded-full bg-[#27c93f]" />
            <span className="ml-2">{title}</span>
            {right && <span className="ml-auto">{right}</span>}
        </div>
    );
}

function UploadPanel() {
    return (
        <div className="mockup-dark text-foreground bg-card/70 backdrop-blur-md border border-primary/25 rounded-2xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.25)]">
            <WindowChrome title="Upload match footage" />
            <div className="m-4 border-2 border-dashed border-primary/25 rounded-xl p-6 text-center bg-primary/[0.04]">
                <div className="flex justify-center mb-2.5 text-primary">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
                        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                </div>
                <p className="text-sm font-bold mb-1">Drop your match video here</p>
                <p className="text-xs text-muted-foreground mb-3">MP4, MOV or AVI · up to 2 GB</p>
                <span className="inline-block px-4 py-1.5 bg-primary text-primary-foreground text-xs font-semibold rounded-lg">Choose file</span>
            </div>
        </div>
    );
}

function ProcessingPanel() {
    const steps = [
        { label: "Court detection",     pct: 100, done: true },
        { label: "Player tracking",     pct: 100, done: true },
        { label: "Shuttle tracking",    pct: 72,  pulse: true },
        { label: "Shot classification", pct: 0,   waiting: true },
    ];
    return (
        <div className="mockup-dark text-foreground bg-card/70 backdrop-blur-md border border-primary/25 rounded-2xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.25)]">
            <WindowChrome title="Analysing footage…" />
            <div className="p-4 space-y-3">
                <div className="bg-black rounded-lg h-32 relative overflow-hidden">
                    <svg className="absolute inset-0 w-full h-full" viewBox="0 0 400 130" preserveAspectRatio="xMidYMid slice">
                        <rect width="400" height="130" fill="#060d14" />
                        <rect x="60" y="10" width="280" height="110" fill="rgba(22,78,46,0.5)" stroke="rgba(255,255,255,0.4)" strokeWidth="1" />
                        <line x1="60" y1="65" x2="340" y2="65" stroke="rgba(255,255,255,0.7)" strokeWidth="1.5" />
                        <circle cx="150" cy="32" r="4" fill="#F5F5F4" />
                        <circle cx="260" cy="90" r="4" fill="#A3A3A3" />
                        <circle cx="205" cy="58" r="3" fill="#fff" /><circle cx="205" cy="58" r="6" fill="rgba(255,255,255,0.12)" />
                    </svg>
                </div>
                <div className="space-y-2">
                    {steps.map((s) => (
                        <div key={s.label} className="flex items-center gap-2.5 text-[12px]">
                            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: s.done ? "#10b981" : s.pulse ? "var(--color-primary)" : "#424960" }} />
                            <span className="flex-1 text-muted-foreground">{s.label}</span>
                            <div className="w-20 h-[3px] bg-white/[0.06] rounded-full overflow-hidden">
                                <div className="h-full rounded-full" style={{ width: `${s.pct}%`, background: s.done ? "#10b981" : s.pulse ? "var(--color-primary)" : "transparent" }} />
                            </div>
                            <span className={`text-[11px] font-semibold w-7 text-right ${s.done ? "text-[#10b981]" : s.pulse ? "text-primary" : "text-muted-foreground"}`}>
                                {s.done ? "Done" : s.pulse ? "72%" : "—"}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function ResultsPanel() {
    const shots = [
        { t: "0:12", color: "var(--color-primary)", name: "Clear", pos: "3.1, 1.2", hi: true },
        { t: "0:15", color: "#f59e0b", name: "Smash", pos: "4.8, 0.6" },
        { t: "0:17", color: "#10b981", name: "Drop",  pos: "2.9, 2.1" },
        { t: "0:21", color: "#8b5cf6", name: "Net",   pos: "3.2, 3.8" },
    ];
    return (
        <div className="mockup-dark text-foreground bg-card/70 backdrop-blur-md border border-primary/25 rounded-2xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.25)]">
            <WindowChrome title="Results" right={<span className="text-primary font-bold">47 shots</span>} />
            <div className="p-3.5 space-y-2">
                <div className="grid grid-cols-3 gap-2">
                    {([["Shots","47","text-primary"],["Rallies","8",""],["Time","4:12",""]] as [string,string,string][]).map(([l,v,c]) => (
                        <div key={l} className="bg-white/[0.03] border border-border rounded-lg p-2 text-center">
                            <div className="text-[8px] font-bold uppercase tracking-wide text-muted-foreground mb-1">{l}</div>
                            <div className={`text-lg font-black tabular-nums ${c}`}>{v}</div>
                        </div>
                    ))}
                </div>
                <div>
                    {shots.map((s) => (
                        <div key={s.t} className={`flex items-center gap-2 px-2 py-1.5 rounded text-[11px] border-b border-white/[0.04] ${s.hi ? "bg-primary/10 border-l-2 border-primary" : ""}`}>
                            <span className="text-primary font-bold w-7 flex-shrink-0">{s.t}</span>
                            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: s.color }} />
                            <span className={`font-semibold flex-1 ${s.hi ? "text-primary" : "text-muted-foreground"}`}>{s.name}</span>
                            <span className="text-[9px] text-muted-foreground tabular-nums">{s.pos}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function ShotLogPanel() {
    const rows = [
        { t: "0:12", color: "var(--color-primary)", name: "Clear", pos: "3.1, 1.2", hi: true },
        { t: "0:15", color: "#f59e0b", name: "Smash", pos: "4.8, 0.6" },
        { t: "0:17", color: "#10b981", name: "Drop",  pos: "2.9, 2.1" },
        { t: "0:21", color: "#8b5cf6", name: "Net",   pos: "3.2, 3.8" },
        { t: "0:24", color: "#f59e0b", name: "Smash", pos: "5.1, 0.4" },
        { t: "0:28", color: "var(--color-primary)", name: "Clear", pos: "1.8, 1.9" },
    ];
    return (
        <div className="mockup-dark text-foreground bg-card/70 backdrop-blur-md border border-primary/25 rounded-2xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.25)]">
            <WindowChrome title="Shot Log" right={<span className="text-primary font-bold">47</span>} />
            <div className="p-3">
                {rows.map((r) => (
                    <div key={r.t + r.name} className={`flex items-center gap-2 px-2 py-1.5 rounded text-[11px] border-b border-white/[0.04] ${r.hi ? "bg-primary/10 border-l-2 border-l-primary" : ""}`}>
                        <span className="text-primary font-bold w-7 flex-shrink-0">{r.t}</span>
                        <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: r.color }} />
                        <span className={`font-semibold flex-1 ${r.hi ? "text-primary" : "text-muted-foreground"}`}>{r.name}</span>
                        <span className="text-[9px] text-muted-foreground tabular-nums">{r.pos}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

function HeatmapPanel() {
    const legend = [
        { color: "var(--color-primary)", label: "Clear", w: "100%", n: 19 },
        { color: "#f59e0b", label: "Smash", w: "68%", n: 13 },
        { color: "#8b5cf6", label: "Net",   w: "42%", n: 8  },
        { color: "#10b981", label: "Drop",  w: "28%", n: 6  },
    ];
    return (
        <div className="mockup-dark text-foreground bg-card/70 backdrop-blur-md border border-primary/25 rounded-2xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.25)]">
            <WindowChrome title="Shot Heatmap" />
            <div className="p-3 flex gap-3 items-start">
                <svg viewBox="0 0 130 272" className="w-[72px] h-[150px] flex-shrink-0">
                    <rect width="130" height="272" fill="rgba(8,16,28,0.9)" rx="4" />
                    <rect x="16" y="20" width="98" height="232" fill="rgba(22,78,46,0.8)" />
                    <rect x="16" y="20" width="98" height="232" fill="none" stroke="rgba(255,255,255,0.8)" strokeWidth="1.2" />
                    <line x1="16" y1="136" x2="114" y2="136" stroke="rgba(255,255,255,0.9)" strokeWidth="2" />
                    <line x1="16" y1="105" x2="114" y2="105" stroke="rgba(255,255,255,0.3)" strokeWidth="0.8" />
                    <line x1="16" y1="167" x2="114" y2="167" stroke="rgba(255,255,255,0.3)" strokeWidth="0.8" />
                    <circle cx="32" cy="45" r="3.5" fill="var(--color-primary)" opacity="0.85" />
                    <circle cx="80" cy="55" r="3.5" fill="var(--color-primary)" opacity="0.85" />
                    <circle cx="55" cy="40" r="3.5" fill="var(--color-primary)" opacity="0.85" />
                    <circle cx="72" cy="115" r="3.5" fill="#f59e0b" opacity="0.85" />
                    <circle cx="38" cy="125" r="3.5" fill="#f59e0b" opacity="0.85" />
                    <circle cx="60" cy="230" r="3.5" fill="#10b981" opacity="0.85" />
                    <circle cx="45" cy="220" r="3.5" fill="#10b981" opacity="0.85" />
                    <circle cx="65" cy="180" r="3.5" fill="#8b5cf6" opacity="0.85" />
                    <circle cx="52" cy="175" r="3.5" fill="#8b5cf6" opacity="0.85" />
                    <circle cx="30" cy="200" r="3.5" fill="var(--color-primary)" opacity="0.85" />
                </svg>
                <div className="flex-1 flex flex-col justify-center gap-2.5 py-1">
                    {legend.map((l) => (
                        <div key={l.label} className="flex items-center gap-2 text-[11px]">
                            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: l.color }} />
                            <span className="text-muted-foreground w-10 flex-shrink-0">{l.label}</span>
                            <div className="flex-1 h-[3px] bg-white/[0.06] rounded-full overflow-hidden">
                                <div className="h-full rounded-full" style={{ width: l.w, background: l.color }} />
                            </div>
                            <span className="font-bold w-4 text-right tabular-nums">{l.n}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function RallyPanel() {
    const dots1 = ["var(--color-primary)", "#f59e0b", "#10b981", "var(--color-primary)", "#f59e0b", "#8b5cf6", "var(--color-primary)", "#f59e0b"];
    const dots2 = ["var(--color-primary)", "#10b981", "var(--color-primary)", "#f59e0b", "#8b5cf6", "var(--color-primary)"];
    return (
        <div className="mockup-dark text-foreground bg-card/70 backdrop-blur-md border border-primary/25 rounded-2xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.25)]">
            <WindowChrome title="Rally Analysis" right={<span>8 rallies</span>} />
            <div className="p-3 space-y-3">
                <div className="grid grid-cols-4 gap-1.5">
                    {([["Rallies","8","text-primary"],["Longest","14","text-amber-400"],["Avg","5.8",""],["&gt;5","62%","text-emerald-400"]] as [string,string,string][]).map(([l,v,c]) => (
                        <div key={l} className="bg-white/[0.04] border border-border rounded-lg p-2 text-center">
                            <div className="text-[8px] font-bold uppercase tracking-wide text-muted-foreground mb-0.5">{l.replace("&gt;", ">")}</div>
                            <div className={`text-sm font-black ${c}`}>{v}</div>
                        </div>
                    ))}
                </div>
                {[
                    { n:"#1", time:"0:12–0:35", grad:"linear-gradient(90deg,#f59e0b,#d97706)", w:"100%", shots:14, c:"text-amber-400", dots:dots1 },
                    { n:"#2", time:"0:42–0:58", grad:"linear-gradient(90deg,var(--color-primary),#737373)", w:"64%", shots:9, c:"", dots:dots2 },
                ].map((r) => (
                    <div key={r.n} className="flex items-center gap-2.5 text-[11px] border-b border-white/[0.05] pb-2">
                        <span className="text-muted-foreground font-bold w-4">{r.n}</span>
                        <div className="flex-1">
                            <div className="text-[9px] text-muted-foreground mb-1">{r.time}</div>
                            <div className="h-[3px] bg-white/[0.06] rounded-full overflow-hidden mb-1.5">
                                <div className="h-full rounded-full" style={{ width: r.w, background: r.grad }} />
                            </div>
                            <div className="flex gap-1">
                                {r.dots.map((d, i) => <span key={i} className="w-1.5 h-1.5 rounded-full" style={{ background: d }} />)}
                            </div>
                        </div>
                        <div className="text-right">
                            <div className={`text-sm font-black ${r.c}`}>{r.shots}</div>
                            <div className="text-[9px] text-muted-foreground">shots</div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ── Main page ─────────────────────────────────────────────────────────────────

// One button system for the page: a solid primary and an outlined secondary,
// same shape and label size, each with a visible keyboard focus ring.
const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const BTN_BASE = `cursor-pointer inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-[translate,background-color] duration-150 hover:-translate-y-0.5 active:translate-y-0 ${FOCUS}`;
const BTN_PRIMARY = `${BTN_BASE} bg-primary text-primary-foreground hover:bg-primary/90`;
const BTN_SECONDARY = `${BTN_BASE} bg-white dark:bg-card text-slate-700 dark:text-slate-200 border border-slate-300 dark:border-border hover:bg-slate-50 dark:hover:bg-white/10`;
const BTN_LG = "px-7 py-3.5 text-[15px]";
const BTN_SM = "px-4 py-2 text-sm";

const MAIN_ACTION = "Analyse a match";


const HOW_STEPS = [
    { n: "1", title: "Upload a match recording", desc: "Drop one match recording into your dashboard.", panel: <UploadPanel /> },
    { n: "2", title: "Shuttleye tracks the rally", desc: "It maps the court, follows the shuttle frame by frame and tracks both players.", panel: <ProcessingPanel /> },
    { n: "3", title: "Read the match report", desc: "Shot log, court heatmap and rally breakdown, all linked to the video.", panel: <ResultsPanel /> },
];

const FEATURES = [
    {
        title: "Shot log: every hit in the match, timed and typed",
        desc: "Each hit is labelled clear, smash, drop, drive, net or lob, with its time in the video and its court position.",
        bullets: ["Click a row to jump to that hit in the video", "The current shot highlights as the video plays", "Filter the log by shot type"],
        panel: <ShotLogPanel />, reverse: false,
    },
    {
        title: "Court heatmap: where each shot in the match was played",
        desc: "Shuttleye finds the court lines in your video and places every shot on a top-down court.",
        bullets: ["Court geometry detected from the video", "Filter the dots by shot type", "See which zones you rely on"],
        panel: <HeatmapPanel />, reverse: true,
    },
    {
        title: "Rally breakdown: each rally in the match, shot by shot",
        desc: "Rallies are grouped and ranked by length, with the sequence of shot types for each one.",
        bullets: ["Click a rally to jump to it in the video", "Coloured dots show the shot sequence", "Total, longest and average rally length"],
        panel: <RallyPanel />, reverse: false,
    },
];

export default function LandingPage() {
    const navigate = useNavigate();
    const { user, loading } = useAuthUser();
    const { isDark, toggle } = useTheme();

    useEffect(() => {
        if (!loading && user) navigate("/dashboard", { replace: true });
    }, [user, loading, navigate]);

    if (loading || user) {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center">
                <div className="w-10 h-10 border-[3px] border-primary border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <MotionConfig reducedMotion="user">
        <div className="min-h-screen bg-background text-foreground overflow-x-hidden">

            <a href="#main" className={`sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-card focus:text-foreground focus:border focus:border-border ${FOCUS}`}>
                Skip to content
            </a>

            {/* Background */}
            <div className="fixed inset-0 pointer-events-none" aria-hidden="true">
                <div className="dot-grid absolute inset-0 opacity-[0.45]" style={{ backgroundSize: "22px 22px" }} />
            </div>

            {/* Navbar */}
            <nav className="sticky top-0 z-50 w-full bg-white/90 dark:bg-background/90 backdrop-blur-xl border-b border-slate-200 dark:border-border">
                <div className="max-w-7xl mx-auto px-6 h-[70px] flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <span className="text-[17px] font-semibold tracking-tight">Shuttleye</span>
                    </div>
                    <div className="flex items-center gap-3">
                        <button onClick={toggle} aria-label="Toggle dark mode" className={`cursor-pointer relative w-10 h-10 flex items-center justify-center rounded-lg text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10 hover:text-foreground transition-all duration-150 ${FOCUS}`}>
                            <Sun className={`absolute w-4 h-4 transition-all duration-200 ${isDark ? "opacity-0 rotate-90 scale-50" : "opacity-100 rotate-0 scale-100"}`} />
                            <Moon className={`absolute w-4 h-4 transition-all duration-200 ${isDark ? "opacity-100 rotate-0 scale-100" : "opacity-0 -rotate-90 scale-50"}`} />
                        </button>
                        <button onClick={() => navigate("/signin")} className={`${BTN_SECONDARY} ${BTN_SM}`}>
                            Sign in
                        </button>
                    </div>
                </div>
            </nav>

            <main id="main">

            {/* Hero: one screen below the nav */}
            <section className="relative z-10 min-h-[calc(100svh-70px)] flex items-center px-6 py-16 text-center">
                <motion.div className="max-w-4xl mx-auto" data-enter initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }}>
                    <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.05] mb-6">
                        Badminton match analysis <span className="text-muted-foreground">from your video</span>
                    </h1>
                    <p className="text-lg md:text-xl text-foreground/75 max-w-2xl mx-auto mb-10 leading-relaxed">
                        Upload a match recording. Shuttleye tracks the shuttle, finds every hit and labels it as one of six shot types.
                    </p>
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
                        <button onClick={() => navigate("/signup")} className={`${BTN_PRIMARY} ${BTN_LG}`}>
                            {MAIN_ACTION} <ChevronRight className="w-4 h-4" aria-hidden="true" />
                        </button>
                    </div>
                    <p className="mt-6 text-sm text-foreground/75">MP4, MOV or AVI · up to 2 GB · free to use</p>
                </motion.div>
            </section>

            {/* How it works */}
            <section className="relative z-10 max-w-7xl mx-auto px-6 py-24">
                <div className="text-center mb-14">
                    <div className="text-[11px] font-bold tracking-[2.5px] uppercase text-muted-foreground mb-3">How it works</div>
                    <h2 className="text-4xl font-bold tracking-tight">How Shuttleye analyses a match</h2>
                </div>
                <div className="grid md:grid-cols-3 md:grid-rows-[auto_auto] gap-x-6 gap-y-4">
                    {HOW_STEPS.map((s) => (
                        <div key={s.n} className="grid gap-4 md:row-span-2 md:grid-rows-subgrid">
                            <div className="flex items-start gap-3">
                                <div className="w-7 h-7 rounded-full bg-primary/10 border border-primary/25 text-primary text-xs font-black flex items-center justify-center flex-shrink-0">{s.n}</div>
                                <div>
                                    <h3 className="text-sm font-bold">{s.title}</h3>
                                    <p className="text-sm text-foreground/75 leading-relaxed">{s.desc}</p>
                                </div>
                            </div>
                            {s.panel}
                        </div>
                    ))}
                </div>
            </section>

            {/* Feature deep-dives */}
            <section className="relative z-10 max-w-7xl mx-auto px-6 py-24 space-y-32">
                <div className="text-center">
                    <div className="text-[11px] font-bold tracking-[2.5px] uppercase text-muted-foreground mb-3">The match report</div>
                    <h2 className="text-4xl font-bold tracking-tight">What the Shuttleye report shows</h2>
                </div>
                {FEATURES.map((f) => (
                    <div key={f.title} className={`grid md:grid-cols-2 gap-12 items-center ${f.reverse ? "md:[direction:rtl]" : ""}`}>
                        <div className="md:[direction:ltr]">{f.panel}</div>
                        <div className="md:[direction:ltr]">
                            <h3 className="text-2xl font-bold tracking-tight mb-3">{f.title}</h3>
                            <p className="text-base text-foreground/75 leading-relaxed mb-5">{f.desc}</p>
                            <ul className="space-y-2.5">
                                {f.bullets.map((b) => (
                                    <li key={b} className="flex items-center gap-2.5 text-[15px] text-foreground/75">
                                        <span className="w-1 h-1 rounded-full bg-primary flex-shrink-0" aria-hidden="true" />
                                        {b}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                ))}
            </section>

            {/* Close */}
            <section className="relative z-10 max-w-7xl mx-auto px-6 py-24 text-center">
                <h2 className="text-4xl font-bold tracking-tight mb-4">Analyse your next badminton match</h2>
                <p className="text-foreground/75 text-lg mb-10">Sign up, upload a recording and get the shot log, heatmap and rallies. Free to use.</p>
                <button onClick={() => navigate("/signup")} className={`${BTN_PRIMARY} ${BTN_LG}`}>
                    {MAIN_ACTION} <ChevronRight className="w-4 h-4" aria-hidden="true" />
                </button>
            </section>

            </main>

            <footer className="border-t border-slate-200 dark:border-border py-7">
                <div className="max-w-7xl mx-auto px-6 text-center text-sm text-muted-foreground">
                    © 2026 Shuttleye
                </div>
            </footer>

        </div>
        </MotionConfig>
    );
}
