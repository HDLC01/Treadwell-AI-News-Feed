/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        fg: "var(--fg)",
        muted: "var(--muted)",
        border: "var(--border)",
        primary: {
          DEFAULT: "var(--primary)",
          fg: "var(--primary-fg)",
        },
        secondary: "var(--secondary)",
        accent: {
          DEFAULT: "var(--accent)",
          fg: "var(--accent-fg)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          fg: "var(--destructive-fg)",
        },
        hot: "var(--hot)",
        warm: "var(--warm)",
        cold: "var(--cold)",
        ring: "var(--ring)",
        // On-surface TEXT variants (AA-contrast); fills above are for dots/bg.
        "warm-text": "var(--warm-text)",
        "info-text": "var(--info-text)",
        success: "var(--success)",
      },
      fontFamily: {
        sans: ["Fira Sans", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["Fira Code", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      transitionDuration: {
        DEFAULT: "200ms",
      },
    },
  },
  plugins: [],
};
