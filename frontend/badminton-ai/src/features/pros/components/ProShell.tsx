import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/useTheme";
import { cn } from "@/lib/utils";
import { ProAttribution } from "./ProAttribution";

const focus =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const control = cn(
  "inline-flex min-h-11 items-center whitespace-nowrap rounded-lg px-3 text-sm font-medium transition-colors",
  focus,
);

const links = [
  { to: "/players", label: "Players" },
  { to: "/tournaments", label: "Tournaments" },
];

export function ProShell({ children }: { children: ReactNode }) {
  const { isDark, toggle } = useTheme();

  return (
    <div className="min-h-screen bg-background font-sans text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-[1600px] items-center gap-2 px-4 min-[760px]:px-12">
          <Link
            to="/"
            className={cn(control, "-ml-3 mr-auto text-base font-semibold text-foreground")}
          >
            Shuttleye
          </Link>
          <nav aria-label="Pro data" className="flex items-center">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  cn(
                    control,
                    isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                  )
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
          <button
            type="button"
            onClick={toggle}
            aria-label="Toggle dark mode"
            className={cn(
              "relative inline-flex size-11 cursor-pointer items-center justify-center rounded-lg text-muted-foreground hover:text-foreground",
              focus,
            )}
          >
            <Sun className={cn("absolute size-4", isDark && "opacity-0")} />
            <Moon className={cn("absolute size-4", !isDark && "opacity-0")} />
          </button>
          <Link
            to="/signin"
            className={cn(control, "bg-primary px-3 text-primary-foreground hover:opacity-90")}
          >
            Sign in
          </Link>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1600px] px-4 py-8 min-[760px]:px-12">{children}</main>
      <footer className="mx-auto w-full max-w-[1600px] px-4 pb-10 min-[760px]:px-12">
        <ProAttribution />
      </footer>
    </div>
  );
}
