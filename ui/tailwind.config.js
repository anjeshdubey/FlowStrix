/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: { 0: '#08090b', 1: '#101215', 2: '#191c21' },
        border: { subtle: '#23262c', DEFAULT: '#2e323a', strong: '#3d424c' },
        accent: { DEFAULT: '#2f8aff', glow: 'rgba(47,138,255,0.28)' },
        success: '#34d399',
        warning: '#f5a623',
        danger: '#f2495c',
        muted: '#6b7280',
        info: '#38bdf8',
      },
      textColor: {
        primary: '#f2f4f7',
        secondary: '#a7adba',
        muted: '#6b7280',
      },
      fontFamily: {
        ui: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        1: '12px',
        2: '13px',
        3: '15px',
        4: '18px',
        5: '24px',
        6: '34px',
      },
      spacing: { 1: '4px', 2: '8px', 4: '16px', 6: '24px', 8: '32px', 12: '48px' },
      borderRadius: { sm: '4px', md: '8px', lg: '12px', xl: '16px', full: '999px' },
      boxShadow: {
        1: '0 1px 2px rgba(0,0,0,0.4)',
        2: '0 4px 12px rgba(0,0,0,0.5)',
        'glow-accent': '0 0 0 3px rgba(47,138,255,0.2), 0 4px 20px rgba(47,138,255,0.25)',
        'glow-amber': '0 0 0 3px rgba(245,166,35,0.22), 0 4px 20px rgba(245,166,35,0.2)',
      },
      transitionDuration: {
        instant: '60ms',
        stream: '240ms',
        drawer: '320ms',
        dim: '200ms',
      },
      keyframes: {
        streamIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '60%': { opacity: '1', transform: 'translateY(0)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        ringPulse: {
          '0%, 70%, 100%': { boxShadow: '0 0 0 3px rgba(47,138,255,0.22), 0 4px 20px rgba(47,138,255,0.18)' },
          '35%': { boxShadow: '0 0 0 6px rgba(47,138,255,0.10), 0 4px 26px rgba(47,138,255,0.28)' },
        },
        drawerSlide: {
          '0%, 15%': { transform: 'translateX(24px)', opacity: '0.4' },
          '45%, 100%': { transform: 'translateX(0)', opacity: '1' },
        },
        branchDim: {
          '0%, 20%': { opacity: '1' },
          '50%, 85%': { opacity: '0.35' },
          '100%': { opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200px 0' },
          '100%': { backgroundPosition: '200px 0' },
        },
        slideIn: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'stream-in': 'streamIn 240ms ease-out',
        'ring-pulse': 'ringPulse 1800ms ease-in-out infinite',
        'drawer-slide': 'drawerSlide 320ms cubic-bezier(0,0,.2,1)',
        'branch-dim': 'branchDim 200ms ease-out forwards',
        shimmer: 'shimmer 1400ms linear infinite',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-in': 'slideIn 0.3s ease-out',
        'fade-in': 'fadeIn 0.5s ease-out',
      },
    },
  },
  plugins: [],
}
