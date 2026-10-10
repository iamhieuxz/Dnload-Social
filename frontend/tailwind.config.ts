import type { Config } from "tailwindcss";

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
        background: "hsl(240 10% 3.9%)",
        foreground: "hsl(0 0% 98%)",
        card: "hsl(240 10% 5%)",
        "card-foreground": "hsl(0 0% 98%)",
        primary: "hsl(322 75% 60%)",     // Instagram pink
        "primary-foreground": "hsl(0 0% 0%)",
        secondary: "hsl(240 4% 16%)",
        "secondary-foreground": "hsl(0 0% 98%)",
        muted: "hsl(240 5% 11%)",
        "muted-foreground": "hsl(240 5% 65%)",
        accent: "hsl(199 89% 48%)",       // Sky blue
        "accent-foreground": "hsl(0 0% 0%)",
        success: "hsl(160 84% 39%)",
        warning: "hsl(38 92% 50%)",
        destructive: "hsl(0 84% 60%)",
        border: "hsl(240 4% 16%)",
        input: "hsl(240 4% 16%)",
        ring: "hsl(322 75% 60%)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px hsl(322 75% 60% / 0.25)",
        "glow-sm": "0 0 12px hsl(322 75% 60% / 0.2)",
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
