/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: 'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          tertiary: 'var(--bg-tertiary)',
          card: 'var(--bg-card)',
          'card-hover': 'var(--bg-card-hover)',
        },
        accent: {
          terracotta: 'var(--accent-terracotta)',
          forest: 'var(--accent-forest)',
          gold: 'var(--accent-gold)',
          sage: 'var(--accent-sage)',
          rust: 'var(--accent-rust)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          tertiary: 'var(--text-tertiary)',
          muted: 'var(--text-muted)',
        },
        border: {
          subtle: 'var(--border-subtle)',
          medium: 'var(--border-medium)',
          strong: 'var(--border-strong)',
        },
        importance: {
          high: 'var(--importance-high)',
          medium: 'var(--importance-medium)',
          low: 'var(--importance-low)',
        },
        chart: {
          1: 'var(--chart-1)',
          2: 'var(--chart-2)',
          3: 'var(--chart-3)',
          4: 'var(--chart-4)',
          5: 'var(--chart-5)',
          6: 'var(--chart-6)',
          7: 'var(--chart-7)',
        },
      },
      fontFamily: {
        sans: ['Source Sans 3', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        display: ['Cormorant Garamond', 'Georgia', 'serif'],
        mono: ['IBM Plex Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards',
      },
      boxShadow: {
        'editorial': '0 1px 2px rgba(61, 54, 48, 0.04), 0 4px 8px rgba(61, 54, 48, 0.04), 0 12px 24px rgba(61, 54, 48, 0.06)',
        'editorial-hover': '0 2px 4px rgba(61, 54, 48, 0.04), 0 8px 16px rgba(61, 54, 48, 0.06), 0 24px 48px rgba(61, 54, 48, 0.08)',
      },
    },
  },
  plugins: [],
}
