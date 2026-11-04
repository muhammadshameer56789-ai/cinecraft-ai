/** Brand tokens live here so name/theme stay configurable. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1b1a18", panel: "#242220", edge: "#34312d", mist: "#ece8df", dim: "#a39d92",
        gold: "#d9a441", leaf: "#7a9a55", alert: "#e0795f",
      },
      fontFamily: { sans: ["Figtree", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
