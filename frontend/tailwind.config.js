export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        page: '#f2f5f4', ink: '#0e2433', muted: '#52687a', line: '#d6dfe3', brand: '#0d5c63',
        st: { available: '#1a9f63', reserved: '#7c5cdb', plugged: '#d98a00', charging: '#1d6fe0',
              finished: '#0f9bb0', faulted: '#d93d44', offline: '#7d8b96' }
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', 'system-ui', 'sans-serif'],
        body: ['"Hanken Grotesk"', 'system-ui', 'sans-serif']
      }
    }
  },
  plugins: []
}
