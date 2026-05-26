/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#533afd",
        "primary-deep": "#4434d4",
        "primary-press": "#2e2b8c",
        "primary-soft": "#665efd",
        "primary-muted": "#b9b9f9",
        "brand-dark": "#1c1e54",
        ink: "#0d253d",
        "ink-secondary": "#273951",
        "ink-mute": "#64748d",
        canvas: "#ffffff",
        "canvas-soft": "#f6f9fc",
        "canvas-cream": "#f5e9d4",
        hairline: "#e3e8ee",
        "hairline-input": "#a8c3de",
        ruby: "#ea2261",
      },
      fontFamily: {
        sans: ["Inter", "SF Pro Display", "system-ui", "-apple-system", "sans-serif"],
      },
      borderRadius: {
        pill: "9999px",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
