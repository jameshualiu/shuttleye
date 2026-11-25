import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "./context/ThemeContext";
import { useTheme } from "./context/useTheme";
import { HOME_PATH } from "./lib/routes";

// FE-15: lazy-load every route (including ProtectedRoute/PrivateLayout --
// ProtectedRoute pulls in firebase/auth via useAuthUser, so leaving it as a
// static import here would still ship Firebase Auth to an anonymous
// landing-page visitor even with the page components split out).
const LandingPage = lazy(() => import("./pages/LandingPage"));
const SignInPage = lazy(() => import("./pages/SignInPage"));
const SignUpPage = lazy(() => import("./pages/SignUpPage"));
const PlayerProfilePage = lazy(() => import("./pages/PlayerProfilePage"));
const PlayersPage = lazy(() => import("./pages/PlayersPage"));
const PairsPage = lazy(() => import("./pages/PairsPage"));
const PairProfilePage = lazy(() => import("./pages/PairProfilePage"));
const TournamentsPage = lazy(() => import("./pages/TournamentsPage"));
const TournamentPage = lazy(() => import("./pages/TournamentPage"));
const MatchPage = lazy(() => import("./pages/MatchPage"));
const ProtectedRoute = lazy(() => import("./auth/ProtectedRoute"));
const PrivateLayout = lazy(() => import("./layouts/PrivateLayout"));

function RouteFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background text-foreground">
      <div className="text-sm text-muted-foreground">Loading…</div>
    </div>
  );
}

function ThemedApp() {
  const { isDark } = useTheme();
  return (
    <div className={`theme-ai-saas min-h-screen bg-background text-foreground${isDark ? " dark" : ""}`}>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/signin" element={<SignInPage />} />
          <Route path="/signup" element={<SignUpPage />} />

          <Route
            element={
              <ProtectedRoute>
                <PrivateLayout />
              </ProtectedRoute>
            }
          >
            {/* Sessions and upload are hidden for now (#71): DashboardPage and
                AnalysisPage stay in the codebase but aren't routed. */}
            <Route path="/dashboard" element={<Navigate to={HOME_PATH} replace />} />
            <Route path="/analysis/:videoId" element={<Navigate to={HOME_PATH} replace />} />
            <Route path="/players" element={<PlayersPage />} />
            <Route path="/players/:playerId" element={<PlayerProfilePage />} />
            <Route path="/pairs" element={<PairsPage />} />
            <Route path="/pairs/:pairId" element={<PairProfilePage />} />
            <Route path="/tournaments" element={<TournamentsPage />} />
            <Route path="/tournaments/:editionId" element={<TournamentPage />} />
            <Route path="/matches/:matchId" element={<MatchPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <ThemedApp />
    </ThemeProvider>
  );
}
