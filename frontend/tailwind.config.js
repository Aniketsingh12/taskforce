/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b0e14",
        panel: "#131722",
        edge: "#222838",
        accent: "#5b8cff",
      },
    },
  },
  plugins: [],
};
