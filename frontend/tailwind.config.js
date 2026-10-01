/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx}",
    "./components/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff", 100: "#dae5ff", 200: "#bdd0ff", 300: "#8fb0ff",
          400: "#5a85fc", 500: "#3563f4", 600: "#2146e0", 700: "#1b36b6",
          800: "#1c3090", 900: "#1c2d72",
        },
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Segoe UI", "PingFang SC",
               "Hiragino Sans GB", "Microsoft YaHei", "sans-serif"],
      },
    },
  },
  plugins: [],
};
