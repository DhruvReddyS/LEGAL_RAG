/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  // Colours and type live in app/globals.css as tokens, so both themes resolve them.
  theme: { extend: {} },
  plugins: [],
};
