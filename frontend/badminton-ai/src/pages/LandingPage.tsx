import { useNavigate } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { BarChart3, ChevronDown, ChevronRight, Moon, ScanLine, Sparkles, Sun, Upload } from "lucide-react";
import { useAuthUser } from "../auth/hooks/useAuthUser";
import { useTheme } from "../context/useTheme";
import { RallyLog } from "../features/analysis/components/RallyLog";
import { ShotStatsTab } from "../features/analysis/components/ShotStatsTab";
import { useCurrentTimeStore } from "../features/analysis/hooks/useCurrentTimeStore";
import { groupRallies } from "../features/analysis/rallies";
import { DemoHero } from "../features/landing/DemoHero";
import { useDemoAnalysis } from "../features/landing/useDemoAnalysis";
import { useDemoPlayback } from "../features/landing/useDemoPlayback";

// ── Content ───────────────────────────────────────────────────────────────────

const STEPS = [
    { icon: Upload, title: "Upload your match", desc: "Add a video of your game from your dashboard." },
    { icon: ScanLine, title: "We analyse it", desc: "Shuttleye finds the court, follows the shuttle and players, and classifies every shot." },
    { icon: BarChart3, title: "Review and improve", desc: "Open your shot log, court heatmap and rally breakdown." },
];

const fade = { initial: { opacity: 0, y: 24 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true }, transition: { duration: 0.5 } };

export default function LandingPage() {
    const navigate = useNavigate();
    const { user, loading } = useAuthUser();
    const { isDark, toggle } = useTheme();

    const demo = useDemoAnalysis();
    const store = useCurrentTimeStore();
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const [demoEl, setDemoEl] = useState<HTMLDivElement | null>(null);
    const ready = demo.status === "ready" ? demo : null;
    const { showPlayButton, start } = useDemoPlayback(videoRef, demoEl, !!ready);
    const rallies = useMemo(() => (ready ? groupRallies(ready.data.events, ready.fps) : []), [ready]);

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

    const replayRally = (sec: number) => {
        if (videoRef.current) videoRef.current.currentTime = sec;
        start();
        demoEl?.scrollIntoView({ behavior: "smooth", block: "center" });
    };

    return (
        <div className="min-h-screen bg-background text-foreground overflow-x-hidden">

            {/* Background */}
            <div className="fixed inset-0 pointer-events-none" aria-hidden="true">
                <div className="dot-grid absolute inset-0 opacity-[0.45]" style={{ backgroundSize: "22px 22px" }} />
                <div className="absolute -top-32 -right-32 w-[600px] h-[600px] rounded-full bg-primary/8 blur-[100px]" />
                <div className="absolute -bottom-24 -left-24 w-[500px] h-[500px] rounded-full bg-primary/6 blur-[90px]" />
            </div>

            {/* Navbar */}
            <nav className="sticky top-0 z-50 w-full bg-white/90 dark:bg-background/90 backdrop-blur-xl border-b border-slate-200 dark:border-border">
                <div className="max-w-[1400px] mx-auto px-4 sm:px-8 h-[70px] flex items-center justify-between">
                    <motion.div className="flex items-center gap-2" initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }}>
                        <div className="p-1.5 bg-primary/10 border border-primary/20 rounded-lg">
                            <Sparkles className="w-4 h-4 text-primary" />
                        </div>
                        <span className="text-[17px] font-semibold tracking-tight">Shuttleye</span>
                    </motion.div>
                    <motion.div className="flex items-center gap-3" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }}>
                        <button onClick={toggle} aria-label="Toggle dark mode" className="cursor-pointer relative w-8 h-8 flex items-center justify-center rounded-lg text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10 hover:text-foreground transition-all duration-150">
                            <Sun className={`absolute w-4 h-4 transition-all duration-200 ${isDark ? "opacity-0 rotate-90 scale-50" : "opacity-100 rotate-0 scale-100"}`} />
                            <Moon className={`absolute w-4 h-4 transition-all duration-200 ${isDark ? "opacity-100 rotate-0 scale-100" : "opacity-0 -rotate-90 scale-50"}`} />
                        </button>
                        <button onClick={() => navigate("/signin")} className="cursor-pointer px-5 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 hover:-translate-y-0.5 active:translate-y-0 transition-all duration-150">
                            Sign In
                        </button>
                    </motion.div>
                </div>
            </nav>

            {/* Hero + live demo */}
            <section className="relative z-10 pt-20 md:pt-28 px-4 sm:px-6">
                <div className="max-w-3xl mx-auto text-center">
                    <motion.h1 className="text-6xl md:text-8xl font-bold tracking-tight leading-[1.05] mb-6" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.2 }}>
                        Elevate Your<br /><span className="text-primary">Game</span>
                    </motion.h1>
                    <motion.p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.3 }}>
                        Upload a match video. Shuttleye logs every shot, maps where you hit from, and breaks down your rallies so you know what to work on.
                    </motion.p>
                    <motion.div className="flex flex-col sm:flex-row items-center justify-center gap-3" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.4 }}>
                        <button onClick={() => navigate("/signup")} className="cursor-pointer flex items-center gap-2 px-8 py-3.5 bg-primary text-primary-foreground rounded-xl font-semibold hover:-translate-y-0.5 active:translate-y-0 transition-all duration-150">
                            Get started free <ChevronRight className="w-4 h-4" />
                        </button>
                        <a href="#learn" className="flex items-center gap-2 px-8 py-3.5 text-slate-700 dark:text-slate-200 rounded-xl font-semibold hover:bg-slate-100 dark:hover:bg-white/10 transition-colors duration-150">
                            See what you'll learn <ChevronDown className="w-4 h-4" />
                        </a>
                    </motion.div>
                </div>

                <DemoHero ref={setDemoEl} demo={demo} store={store} videoRef={videoRef} showPlayButton={showPlayButton} onPlay={start} />
            </section>

            {/* What you'll learn */}
            <section id="learn" className="relative z-10 max-w-6xl mx-auto px-4 sm:px-6 pt-32 pb-8 scroll-mt-24">
                <motion.div className="max-w-2xl mb-16" {...fade}>
                    <div className="text-[11px] font-bold tracking-[2.5px] uppercase text-primary mb-3">What you'll learn</div>
                    <h2 className="text-3xl md:text-4xl font-bold tracking-tight">The same match, from every angle</h2>
                </motion.div>

                <div className="relative space-y-24 lg:pl-16">
                    {/* Thread joining the steps */}
                    <div className="hidden lg:block absolute left-[19px] top-2 bottom-2 w-px bg-gradient-to-b from-primary/50 via-primary/20 to-transparent" aria-hidden="true" />

                    {/* Full width: ShotStatsTab is laid out for the analysis page's width,
                        and its heatmap legend clips when squeezed into a split column. */}
                    <motion.div className="relative space-y-8" {...fade}>
                        <FeatureText
                            n="01"
                            title="See where you play"
                            desc="Every shot is placed on the court. Filter by shot type to spot the zones you rely on, and the ones you never use."
                            bullets={["Court heatmap of every shot", "How often you play each shot", "Which shots you follow with which"]}
                        />
                        {ready && (
                            <ScaledPanel>
                                <ShotStatsTab shotEvents={ready.data.events} totalShots={ready.data.events.length} status="done" />
                            </ScaledPanel>
                        )}
                    </motion.div>

                    <motion.div className="relative grid lg:grid-cols-[2fr_3fr] gap-8 lg:gap-12 items-start" {...fade}>
                        <FeatureText
                            n="02"
                            title="Understand your rallies"
                            desc="Rallies are grouped and ranked by length, with the shot sequence for each one. Click a rally to replay it in the demo above."
                            bullets={["Longest and average rally length", "Shot-by-shot sequence for each rally", "Jump straight to any rally in your video"]}
                        />
                        {ready && <RallyLog rallies={rallies} fps={ready.fps} onSeek={replayRally} />}
                    </motion.div>
                </div>
            </section>

            {/* How it works */}
            <section className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 py-28">
                <motion.h2 className="text-center text-sm font-bold tracking-[2.5px] uppercase text-primary mb-12" {...fade}>How it works</motion.h2>
                <ol className="grid md:grid-cols-3 gap-10 md:gap-6">
                    {STEPS.map((s, i) => (
                        <motion.li key={s.title} className="relative text-center px-4" {...fade} transition={{ duration: 0.5, delay: i * 0.1 }}>
                            {i < STEPS.length - 1 && (
                                <div className="hidden md:block absolute top-6 left-[calc(50%+36px)] right-[calc(-50%+36px)] h-px bg-border" aria-hidden="true" />
                            )}
                            <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-primary/10 border border-primary/25 text-primary flex items-center justify-center">
                                <s.icon className="w-5 h-5" />
                            </div>
                            <div className="font-semibold mb-1.5">{s.title}</div>
                            <p className="text-sm text-muted-foreground leading-relaxed">{s.desc}</p>
                        </motion.li>
                    ))}
                </ol>
            </section>

            {/* CTA */}
            <motion.section className="relative z-10 max-w-4xl mx-auto px-4 sm:px-6 pb-28" {...fade}>
                <div className="rounded-3xl border border-primary/25 bg-primary/[0.06] px-6 py-14 text-center">
                    <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">Find out how you really play</h2>
                    <p className="text-muted-foreground text-lg mb-9">Upload your first match and see it shot by shot.</p>
                    <button onClick={() => navigate("/signup")} className="cursor-pointer inline-flex items-center gap-2 px-8 py-4 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl font-semibold hover:-translate-y-0.5 active:translate-y-0 transition-all duration-150">
                        Get started free <ChevronRight className="w-5 h-5" />
                    </button>
                </div>
            </motion.section>

            {/* Footer */}
            <footer className="relative z-10 border-t border-slate-200 dark:border-border py-7">
                <div className="max-w-7xl mx-auto px-6 text-center text-sm text-muted-foreground">
                    © 2026 Shuttleye
                </div>
            </footer>
        </div>
    );
}

function FeatureText({ n, title, desc, bullets }: { n: string; title: string; desc: string; bullets: string[] }) {
    return (
        <div className="lg:pt-2 max-w-xl">
            <div className="lg:absolute lg:-left-16 lg:top-0 w-10 h-10 mb-4 lg:mb-0 rounded-full bg-background border border-primary/40 text-primary text-xs font-black flex items-center justify-center">
                {n}
            </div>
            <h3 className="text-2xl font-bold tracking-tight mb-3">{title}</h3>
            <p className="text-[15px] text-muted-foreground leading-relaxed mb-5">{desc}</p>
            <ul className="space-y-2.5">
                {bullets.map((b) => (
                    <li key={b} className="flex items-center gap-2.5 text-[13px] text-muted-foreground">
                        <span className="w-1 h-1 rounded-full bg-primary flex-shrink-0" />
                        {b}
                    </li>
                ))}
            </ul>
        </div>
    );
}

// ShotStatsTab's two-column grids need ~650px before the heatmap legend clips;
// below that, zoom it down instead of letting it overflow.
function ScaledPanel({ children }: { children: React.ReactNode }) {
    return <div className="[zoom:0.5] sm:[zoom:0.85] md:[zoom:1]">{children}</div>;
}
