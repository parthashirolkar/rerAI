import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1a1f1d",
        sage: "#dfe7df",
        fern: "#4f7a5a",
        clay: "#b0694f",
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'IBM Plex Sans'", "sans-serif"],
      },
      backgroundImage: {
        "wash-gradient": "radial-gradient(circle at 20% 20%, #f6f9f4 0%, #e6ede3 45%, #d6dfd4 100%)",
      },
    },
  },
  plugins: [],
} satisfies Config;
