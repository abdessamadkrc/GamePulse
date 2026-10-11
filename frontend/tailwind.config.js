/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)', panel: 'var(--panel)', panel2: 'var(--panel-2)', line: 'var(--line)',
        ink: 'var(--ink)', ink2: 'var(--ink-2)', ink3: 'var(--ink-3)', accent: 'var(--accent)',
        good: 'var(--good)', bad: 'var(--bad)', warn: 'var(--warn)',
      },
      fontFamily: {
        display: ['"Chakra Petch"', 'system-ui', 'sans-serif'],
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};
