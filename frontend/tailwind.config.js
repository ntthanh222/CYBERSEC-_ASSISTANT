/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--bg-primary)",
        surface: "var(--bg-surface)",
        "surface-container": "var(--bg-surface-container)",
        "surface-container-low": "var(--bg-surface-low)",
        "surface-container-high": "var(--bg-surface-high)",
        "surface-container-highest": "var(--bg-surface-highest)",
        primary: "var(--color-accent)",
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-muted": "var(--text-muted)",
        critical: "var(--color-critical)",
        high: "var(--color-high)",
        medium: "var(--color-medium)",
        low: "var(--color-low)",
        info: "var(--color-info)",
        success: "var(--color-success)",
        warning: "var(--color-warning)",
      },
      fontFamily: {
        headline: "var(--font-headline)",
        body: "var(--font-body)",
        mono: "var(--font-mono)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
      boxShadow: {
        subtle: "var(--shadow-subtle)",
        elevated: "var(--shadow-elevated)",
      },
    },
  },
  plugins: [],
}
