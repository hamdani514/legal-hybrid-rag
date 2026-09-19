/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      "colors": {
              // ══ Brand system, matched to the AI Resume Lab reference ══
              // Primary #0085ff is the reference's signature blue (108 uses
              // in its stylesheet); 2400ff is the violet it gradients into.
              // Measured before shipping: ash-600 on white 7.6:1, brand-700
              // on brand-50 6.0:1, white on brand-600 4.6:1.
              "brand": {
                "50": "#f5faff",
                "100": "#e0f0ff",
                "200": "#bae0ff",
                "300": "#7cc5ff",
                "400": "#38a8ff",
                "500": "#0085ff",
                "600": "#0074e4",
                "700": "#0065c7",
                "800": "#0050cc",
                "900": "#003d99",
              },
              // The gradient terminus and deep-accent violet.
              "violet": {
                "500": "#3813c2",
                "600": "#2400ff",
                "700": "#1f00e0",
              },
              "cyan": {
                "300": "#00cfff",
                "400": "#00c6ff",
                "500": "#00a3ff",
              },
              // Neutrals, cool-biased so they sit under the blue.
              "ash": {
                "50": "#f8fafc",
                "100": "#f1f5f9",
                "150": "#eff2f9",
                "200": "#e5e7eb",
                "300": "#d1d5db",
                "400": "#9ca3af",
                "500": "#6b7280",
                "600": "#4b5563",
                "700": "#374151",
                "800": "#1f2937",
                "900": "#111827",
              },
              "mint": { "400": "#4ade80", "500": "#22c55e", "600": "#16a34a", "700": "#15803d" },
              "amber": { "400": "#ffc700", "500": "#f0b400" },

              // ── Editorial scales ────────────────────────────────────────
              // Named ramps used by the banner, auth and legal components.
              // Anchored to the existing brand: ink-900 is the navy
              // (#0D1C32), gold-400 is the brand gold (#E9C176), and
              // parchment is the warm paper ground that pairs with them.
              // Every value used for text clears 4.5:1 on parchment; the
              // 3:1 pairs (gold-600, ink-400) are only used for icons,
              // hairlines and large metadata.
              "parchment": {
                "50": "#fbfaf7",
                "100": "#f5f2eb",
                "200": "#eae4d8",
              },
              "ink": {
                "50": "#f4f6f9",
                "100": "#e6e9ee",
                "200": "#c9d1dd",
                "300": "#9aa6b8",
                "400": "#7a8799",
                "500": "#5c6878",
                "600": "#454f5f",
                "700": "#2f3a4b",
                "800": "#1c2838",
                "900": "#0d1c32",
              },
              "gold": {
                "50": "#fdf9f0",
                "100": "#faf1dd",
                "200": "#f2deb2",
                "300": "#ebce8e",
                "400": "#e9c176",
                "500": "#d3a44d",
                "600": "#a97c24",
                "700": "#85611b",
                "800": "#5d4201",
              },

              "inverse-on-surface": "#f0f1f3",
              "on-secondary-fixed": "#151c25",
              "surface-container-lowest": "#ffffff",
              "error": "#ba1a1a",
              "secondary-fixed": "#dce3f0",
              "primary": "#000000",
              "secondary-fixed-dim": "#c0c7d3",
              "surface-dim": "#d9dadc",
              "on-secondary": "#ffffff",
              "tertiary-fixed-dim": "#e9c176",
              "background": "#f8f9fb",
              "surface-container": "#edeef0",
              "secondary": "#585f6a",
              "tertiary": "#000000",
              "tertiary-container": "#261900",
              "surface-container-low": "#f3f4f6",
              "primary-fixed": "#d6e3ff",
              "on-primary-container": "#76849f",
              "on-background": "#191c1e",
              "on-secondary-fixed-variant": "#404752",
              "outline": "#75777e",
              "surface-container-high": "#e7e8ea",
              "surface-tint": "#515f78",
              "surface-bright": "#f8f9fb",
              "on-tertiary-fixed-variant": "#5d4201",
              "surface-variant": "#e1e2e4",
              "tertiary-fixed": "#ffdea5",
              "on-surface-variant": "#44474d",
              "on-error": "#ffffff",
              "outline-variant": "#c5c6cd",
              "inverse-surface": "#2e3132",
              "on-tertiary-container": "#a17f3b",
              "on-tertiary": "#ffffff",
              "inverse-primary": "#b9c7e4",
              "on-tertiary-fixed": "#261900",
              "on-primary-fixed-variant": "#39475f",
              "on-secondary-container": "#5e6570",
              "secondary-container": "#dce3f0",
              "primary-fixed-dim": "#b9c7e4",
              "on-primary-fixed": "#0d1c32",
              "surface": "#f8f9fb",
              "error-container": "#ffdad6",
              "primary-container": "#0d1c32",
              "on-error-container": "#93000a",
              "on-primary": "#ffffff",
              "on-surface": "#191c1e",
              "surface-container-highest": "#e1e2e4"
      },
      "borderRadius": {
              "DEFAULT": "0.5rem",
              "sm": "0.375rem",
              "md": "0.5rem",
              "lg": "0.75rem",
              "xl": "1rem",
              "2xl": "1.25rem",
              "3xl": "1.75rem",
              "4xl": "2.25rem",
              "5xl": "2.5rem",
              "full": "9999px"
      },
      "fontFamily": {
              "display": ["Outfit", "system-ui", "sans-serif"],
              "prose": ["Lato", "system-ui", "sans-serif"],
              "ui": ["Outfit", "system-ui", "sans-serif"],
              "mono": ["ui-monospace", "SFMono-Regular", "monospace"],
              // Retained for the admin console and auth screens.
              "headline": ["Outfit", "system-ui", "sans-serif"],
              "body": ["Lato", "system-ui", "sans-serif"],
              "label": ["Outfit", "system-ui", "sans-serif"]
      },
      "maxWidth": {
              // The reading measure for long-form legal prose.
              "measure": "62ch",
              "measure-sm": "48ch"
      },
      "boxShadow": {
              "soft": "0 4px 16px -4px rgba(17,24,39,0.08)",
              "card": "0 12px 32px -12px rgba(17,24,39,0.12)",
              "card-lg": "0 28px 60px -20px rgba(17,24,39,0.18)",
              "glow": "0 10px 30px -8px rgba(0,133,255,0.45)",
              "glow-lg": "0 18px 44px -10px rgba(0,133,255,0.55)"
      }
    },
  },
  plugins: [],
}
