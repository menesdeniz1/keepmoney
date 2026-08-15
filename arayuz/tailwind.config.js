/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Sinyal renkleri analiz katmanıyla birebir: dip / ucuz / pahali
        dip: '#16a34a',
        ucuz: '#ca8a04',
        pahali: '#dc2626',
      },
    },
  },
  plugins: [],
}
