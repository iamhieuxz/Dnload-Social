import type { Config } from "tailwindcss";

// Dnload Social design tokens — see docs/REDESIGN-PLAN.md §4.
// Semantic names (background, card, primary, muted, border...) are kept so
// existing pages keep working; values come from the plan palette.
const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Raw plan palette
        ground: "#0B0B0E",
        "surface-1": "#131318",
        "surface-2": "#1A1A20",
        "surface-3": "#23232B",
        ink: "#F4F4F5",
        "ink-2": "#A1A1AA",
        "ink-3": "#6B6B75",
        accent: "#E8C547",
        "accent-soft": "rgba(232,197,71,0.12)",
        "plat-ig": "#C7A8FF",
        "plat-x": "#6BA6FF",
        "plat-tiktok": "#FF7AA8",

        // Semantic aliases used by existing components
        background: "#0B0B0E",
        foreground: "#F4F4F5",
        card: "#131318",
        "card-hover": "#1A1A20",
        "card-foreground": "#F4F4F5",
        primary: "#E8C547",
        "primary-foreground": "#0B0B0E",
        secondary: "#1A1A20",
        "secondary-foreground": "#F4F4F5",
        muted: "#1A1A20",
        "muted-foreground": "#A1A1AA",
        success: "#4ADE80",
        "success-foreground": "#0B0B0E",
        info: "hsl(210 90% 60%)",
        "info-foreground": "#0B0B0E",
        warning: "#F5A524",
        "warning-foreground": "#0B0B0E",
        destructive: "#F87171",
        "destructive-foreground": "#FFFFFF",
        border: "rgba(255,255,255,0.07)",
        input: "rgba(255,255,255,0.07)",
        ring: "#E8C547",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        display: ["var(--font-inter-tight)", "var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "Consolas", "monospace"],
      },
      borderRadius: {
        // Plan radius scale: 6 control · 10 card · 14 modal · 20 palette (never above 20)
        card: "10px",
        modal: "14px",
        palette: "20px",
      },
      boxShadow: {
        // Plan elevation: rest / raised / float
        raised: "0 1px 0 rgba(255,255,255,0.04) inset, 0 0 0 1px rgba(255,255,255,0.07)",
        float: "0 12px 32px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.07)",
        card: "0 1px 0 rgba(255,255,255,0.04) inset, 0 0 0 1px rgba(255,255,255,0.07)",
      },
      animation: {
        "fade-in-up": "fade-in-up 0.4s ease-out backwards",
        shimmer: "shimmer 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
