/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
      },
      colors: {
        brand: {
          blue: '#2563EB',
          navy: '#1E3A5F',
          navydark: '#162D4A',
          teal: '#14B8A6',
        },
      },
    },
  },
  plugins: [],
}
