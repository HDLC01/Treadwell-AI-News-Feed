import { Moon, Sun } from "lucide-react";
import type { Theme } from "../lib/theme";

interface Props {
  theme: Theme;
  onToggle: () => void;
}

export default function ThemeToggle({ theme, onToggle }: Props) {
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className="inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-lg border border-border bg-surface text-fg transition-colors duration-200 hover:bg-muted"
    >
      {isDark ? (
        <Sun className="h-5 w-5" aria-hidden="true" />
      ) : (
        <Moon className="h-5 w-5" aria-hidden="true" />
      )}
    </button>
  );
}
