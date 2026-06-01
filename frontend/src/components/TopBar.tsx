import { useState } from "react";
import { NavLink, Link } from "react-router-dom";
import { Radar, Menu, X } from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import type { Theme } from "../lib/theme";

interface Props {
  theme: Theme;
  onToggleTheme: () => void;
}

const NAV = [
  { to: "/", label: "Feed", end: true },
  { to: "/digests", label: "Digests", end: false },
  { to: "/admin", label: "Admin", end: false },
];

function navClass({ isActive }: { isActive: boolean }): string {
  return [
    "rounded-md px-3 py-2 text-sm font-medium transition-colors duration-200 cursor-pointer",
    isActive
      ? "bg-primary text-primary-fg"
      : "text-fg hover:bg-muted",
  ].join(" ");
}

export default function TopBar({ theme, onToggleTheme }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="mx-auto flex w-full max-w-screen-2xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <Link
          to="/"
          className="flex cursor-pointer items-center gap-2 text-fg transition-opacity duration-200 hover:opacity-90"
          aria-label="Treadwell Radar home"
        >
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-fg">
            <Radar className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="flex flex-col leading-tight">
            <span className="text-base font-bold tracking-tight">
              Treadwell Radar
            </span>
            <span className="hidden text-xs text-cold sm:block">
              Construction-opportunity radar
            </span>
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            className="inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-lg border border-border bg-surface text-fg transition-colors duration-200 hover:bg-muted md:hidden"
          >
            {menuOpen ? (
              <X className="h-5 w-5" aria-hidden="true" />
            ) : (
              <Menu className="h-5 w-5" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {/* Mobile nav */}
      {menuOpen && (
        <nav
          className="border-t border-border bg-surface px-4 py-2 md:hidden"
          aria-label="Mobile"
        >
          <div className="flex flex-col gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setMenuOpen(false)}
                className={navClass}
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        </nav>
      )}
    </header>
  );
}
