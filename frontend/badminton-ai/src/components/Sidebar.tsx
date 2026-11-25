import { useEffect, useId, useRef, useState, type ComponentType, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ChevronUp,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  Trophy,
  User,
  Users,
  Video,
  X,
} from "lucide-react";
import { useAuthUser } from "../auth/hooks/useAuthUser";
import { logout } from "../auth/authActions";
import { useTheme } from "../context/useTheme";
import { cn } from "@/lib/utils";

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  /** Paths that mark this item as the current page. */
  match: (pathname: string) => boolean;
};

const groups: { label: string; items: NavItem[] }[] = [
  {
    label: "Your matches",
    items: [
      {
        to: "/dashboard",
        label: "Sessions",
        icon: Video,
        match: (p) => p === "/dashboard" || p.startsWith("/analysis/"),
      },
    ],
  },
  {
    label: "Pros",
    items: [
      { to: "/players", label: "Singles", icon: User, match: (p) => p.startsWith("/players") },
      { to: "/pairs", label: "Doubles", icon: Users, match: (p) => p.startsWith("/pairs") },
      { to: "/tournaments", label: "Tournaments", icon: Trophy, match: (p) => p.startsWith("/tournaments") },
    ],
  },
];

const focus = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const rowBase = cn(
  "relative flex min-h-10 items-center gap-3 rounded-lg px-3 text-[14px] font-medium transition-colors",
  focus,
);
const rowIdle = "text-muted-foreground hover:bg-muted/60 hover:text-foreground";

type TipProps = {
  label: string;
  /** Only the collapsed rail needs tooltips; otherwise the label is visible. */
  show: boolean;
  children: ReactNode;
};

/** Names an icon-only control on hover and on keyboard focus; Escape hides it (WCAG 1.4.13). */
function Tip({ label, show, children }: TipProps) {
  const [dismissed, setDismissed] = useState(false);
  if (!show) return <>{children}</>;
  return (
    <div
      className="group/tip relative"
      onKeyDown={(e) => {
        if (e.key === "Escape") setDismissed(true);
      }}
      onMouseLeave={() => setDismissed(false)}
      onBlur={() => setDismissed(false)}
    >
      {children}
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute top-1/2 left-full z-50 ml-3 -translate-y-1/2 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background opacity-0 transition-opacity",
          !dismissed && "group-hover/tip:opacity-100 group-has-[:focus-visible]/tip:opacity-100",
        )}
      >
        {label}
      </span>
    </div>
  );
}

type ContentProps = {
  /** Icons only (desktop, collapsed). */
  collapsed: boolean;
  /** Desktop only: shows the collapse / expand button. */
  onToggleCollapsed?: () => void;
};

function SidebarContent({ collapsed, onToggleCollapsed }: ContentProps) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuthUser();
  const { isDark, toggle } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const handleLogout = async () => {
    setMenuOpen(false);
    const res = await logout();
    if (!res.ok) {
      console.error(res.error);
      return;
    }
    navigate("/signin");
  };

  const name = user?.displayName ?? user?.email?.split("@")[0] ?? "Account";
  const initials = user?.displayName
    ? user.displayName
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : (user?.email?.[0]?.toUpperCase() ?? "?");

  return (
    <div className="flex h-full flex-col px-3 py-4">
      <div className={cn("flex h-10 items-center", collapsed ? "justify-center" : "justify-between pl-3")}>
        {!collapsed && (
          <Link to="/dashboard" className={cn("rounded-lg text-[17px] font-semibold tracking-tight", focus)}>
            Shuttleye
          </Link>
        )}
        {onToggleCollapsed && (
          <Tip label={collapsed ? "Expand sidebar" : "Collapse sidebar"} show={collapsed}>
            <button
              type="button"
              onClick={onToggleCollapsed}
              aria-expanded={!collapsed}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              className={cn(
                "flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground",
                focus,
              )}
            >
              {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </button>
          </Tip>
        )}
      </div>

      <nav aria-label="Main" className="mt-6 flex-1">
        {groups.map((group, gi) => (
          <div key={group.label} className={gi > 0 ? "mt-6" : undefined}>
            {collapsed ? (
              gi > 0 && <div aria-hidden="true" className="mx-3 mb-4 border-t border-border" />
            ) : (
              <p className="mb-1.5 px-3 text-xs font-medium text-muted-foreground">{group.label}</p>
            )}
            <ul className="grid gap-0.5">
              {group.items.map((item) => {
                const current = item.match(pathname);
                const Icon = item.icon;
                return (
                  <li key={item.to}>
                    <Tip label={item.label} show={collapsed}>
                      <Link
                        to={item.to}
                        aria-current={current ? "page" : undefined}
                        className={cn(
                          rowBase,
                          collapsed && "justify-center px-0",
                          current
                            ? "bg-muted text-foreground before:absolute before:-left-3 before:top-2 before:bottom-2 before:w-0.5 before:rounded-r before:bg-foreground"
                            : rowIdle,
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        <span className={collapsed ? "sr-only" : undefined}>{item.label}</span>
                      </Link>
                    </Tip>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="grid gap-0.5 border-t border-border pt-3">
        <Tip label={isDark ? "Light mode" : "Dark mode"} show={collapsed}>
          <button
            type="button"
            onClick={toggle}
            className={cn(rowBase, rowIdle, "w-full cursor-pointer", collapsed && "justify-center px-0")}
          >
            {isDark ? <Sun className="h-4 w-4 shrink-0" /> : <Moon className="h-4 w-4 shrink-0" />}
            <span className={collapsed ? "sr-only" : undefined}>{isDark ? "Light mode" : "Dark mode"}</span>
          </button>
        </Tip>

        <div className="relative" ref={menuRef}>
          <Tip label={name} show={collapsed && !menuOpen}>
            <button
              type="button"
              onClick={() => setMenuOpen((o) => !o)}
              aria-expanded={menuOpen}
              aria-controls={menuId}
              className={cn(
                rowBase,
                "w-full cursor-pointer text-foreground hover:bg-muted/60",
                collapsed ? "justify-center px-0" : "pl-2",
              )}
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary text-[11px] font-bold text-primary-foreground">
                {user?.photoURL ? (
                  <img
                    src={user.photoURL}
                    alt=""
                    className="h-full w-full object-cover"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  initials
                )}
              </span>
              <span className={collapsed ? "sr-only" : "min-w-0 flex-1 truncate text-left text-[13px]"}>
                {name}
              </span>
              {!collapsed && (
                <ChevronUp
                  className={cn(
                    "h-3.5 w-3.5 text-muted-foreground transition-transform",
                    !menuOpen && "rotate-180",
                  )}
                />
              )}
            </button>
          </Tip>

          {menuOpen && (
            <div
              id={menuId}
              className="absolute bottom-[calc(100%+6px)] left-0 z-50 min-w-[200px] rounded-xl border border-border bg-popover p-1 shadow-[0_8px_32px_rgba(0,0,0,0.4)]"
            >
              <div className="mb-1 border-b border-border px-3 py-2">
                <div className="truncate text-[12px] font-medium text-foreground">
                  {user?.displayName ?? "Account"}
                </div>
                <div className="truncate text-[11px] text-muted-foreground">{user?.email ?? ""}</div>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                disabled={authLoading}
                className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-destructive/80 transition-colors hover:bg-destructive/10 hover:text-destructive"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

type CollapseChoice = { analysis: boolean | null; other: boolean | null };
const STORAGE_KEY = "shuttleye.sidebar";

function readChoice(): CollapseChoice {
  const none = { analysis: null, other: null };
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as Partial<CollapseChoice> | null;
    const pick = (v: unknown) => (typeof v === "boolean" ? v : null);
    return raw ? { analysis: pick(raw.analysis), other: pick(raw.other) } : none;
  } catch {
    return none;
  }
}

/** Desktop: a fixed left sidebar, collapsible to icons (starts collapsed on the analysis page). */
function DesktopSidebar() {
  const { pathname } = useLocation();
  const isAnalysis = pathname.startsWith("/analysis/");
  // Remember the person's choice separately for the analysis page and everything else.
  const [choice, setChoice] = useState<CollapseChoice>(readChoice);
  const key = isAnalysis ? "analysis" : "other";
  const collapsed = choice[key] ?? isAnalysis;

  const toggleCollapsed = () => {
    const next = { ...choice, [key]: !collapsed };
    setChoice(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Storage blocked: the choice lasts until reload.
    }
  };

  return (
    <aside
      className={cn(
        "sticky top-0 z-40 hidden h-screen shrink-0 border-r border-border transition-[width] duration-200 lg:block",
        collapsed ? "w-[68px]" : "w-[220px]",
      )}
    >
      <SidebarContent collapsed={collapsed} onToggleCollapsed={toggleCollapsed} />
    </aside>
  );
}

/** Below lg: a slim top bar whose menu button opens the sidebar as a drawer. */
function MobileNav() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [lastPath, setLastPath] = useState(pathname);

  // Close the drawer after navigating.
  if (pathname !== lastPath) {
    setLastPath(pathname);
    if (open) setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    const button = buttonRef.current;
    panelRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      // Keep Tab inside the drawer while it's open.
      const items = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>("a[href], button:not([disabled])"),
      );
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !panelRef.current.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !panelRef.current.contains(active))) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      button?.focus();
    };
  }, [open]);

  return (
    <div className="lg:hidden">
      <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b border-border bg-background/90 px-2 backdrop-blur-xl">
        <button
          ref={buttonRef}
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          aria-expanded={open}
          className={cn(
            "flex h-11 w-11 cursor-pointer items-center justify-center rounded-lg text-muted-foreground hover:bg-muted/60 hover:text-foreground",
            focus,
          )}
        >
          <Menu className="h-5 w-5" />
        </button>
        <Link to="/dashboard" className={cn("rounded-lg text-[17px] font-semibold tracking-tight", focus)}>
          Shuttleye
        </Link>
      </header>

      {open && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div
            ref={panelRef}
            className="absolute inset-y-0 left-0 w-[260px] max-w-[85vw] border-r border-border bg-background"
          >
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close menu"
              className={cn(
                "absolute right-2 top-4 flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                focus,
              )}
            >
              <X className="h-5 w-5" />
            </button>
            <SidebarContent collapsed={false} />
          </div>
        </div>
      )}
    </div>
  );
}

export default function Sidebar() {
  return (
    <>
      <DesktopSidebar />
      <MobileNav />
    </>
  );
}
