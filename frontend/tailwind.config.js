/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sand: {
          light: "#f9efe5",
          DEFAULT: "#f5e1d5",
          dark: "#d4b59e"
        },
        garnet: "#6b1f2a",
        amber: "#c47d36",
        onyx: "#1c1c1c"
      },
      fontFamily: {
        display: ["Playfair Display", "serif"],
        body: ["Poppins", "sans-serif"]
      }
    }
  },
  plugins: []
};
