import typography from '@tailwindcss/typography';
import type { Config } from 'tailwindcss';

interface ThemeUtils {
  theme: (path: string) => string;
}

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: [
          'InterVariable',
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'sans-serif',
        ],
      },
      colors: {
        ink: {
          50: '#f6f7f7',
          100: '#e3e7e6',
          200: '#c8d0ce',
          300: '#a4b2af',
          400: '#7b908c',
          500: '#607570',
          600: '#4d5e5a',
          700: '#3f4c49',
          800: '#35403e',
          900: '#2f3736',
          950: '#191e1d',
        },
        accent: {
          50: '#eefbf6',
          100: '#d6f5e7',
          200: '#b0ead3',
          300: '#7bd8b9',
          400: '#45bd9b',
          500: '#279f81',
          600: '#1b8069',
          700: '#196654',
          800: '#185144',
          900: '#16433a',
          950: '#0b2621',
        },
      },
      boxShadow: {
        panel: '0 1px 2px rgba(16, 24, 24, 0.05), 0 8px 24px rgba(16, 24, 24, 0.04)',
      },
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        indeterminate: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(400%)' },
        },
        'message-in': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
        indeterminate: 'indeterminate 1.4s ease-in-out infinite',
        'message-in': 'message-in 0.25s ease-out both',
      },
      typography: ({ theme }: ThemeUtils) => ({
        DEFAULT: {
          css: {
            maxWidth: 'none',
            '--tw-prose-body': theme('colors.ink.800'),
            '--tw-prose-headings': theme('colors.ink.950'),
            '--tw-prose-lead': theme('colors.ink.600'),
            '--tw-prose-links': theme('colors.accent.700'),
            '--tw-prose-bold': theme('colors.ink.950'),
            '--tw-prose-counters': theme('colors.ink.500'),
            '--tw-prose-bullets': theme('colors.ink.400'),
            '--tw-prose-hr': theme('colors.ink.200'),
            '--tw-prose-quotes': theme('colors.ink.700'),
            '--tw-prose-quote-borders': theme('colors.ink.200'),
            '--tw-prose-captions': theme('colors.ink.500'),
            '--tw-prose-code': theme('colors.ink.900'),
            '--tw-prose-pre-code': theme('colors.ink.100'),
            '--tw-prose-pre-bg': theme('colors.ink.950'),
            '--tw-prose-th-borders': theme('colors.ink.300'),
            '--tw-prose-td-borders': theme('colors.ink.200'),
            '> :first-child': { marginTop: '0' },
            '> :last-child': { marginBottom: '0' },
            code: {
              backgroundColor: theme('colors.ink.100'),
              borderRadius: theme('borderRadius.md'),
              paddingInline: '0.35em',
              paddingBlock: '0.1em',
              fontWeight: '500',
            },
            'code::before': { content: 'none' },
            'code::after': { content: 'none' },
          },
        },
        invert: {
          css: {
            '--tw-prose-body': theme('colors.ink.100'),
            '--tw-prose-headings': theme('colors.ink.50'),
            '--tw-prose-lead': theme('colors.ink.300'),
            '--tw-prose-links': theme('colors.accent.400'),
            '--tw-prose-bold': theme('colors.ink.50'),
            '--tw-prose-counters': theme('colors.ink.300'),
            '--tw-prose-bullets': theme('colors.ink.500'),
            '--tw-prose-hr': theme('colors.ink.700'),
            '--tw-prose-quotes': theme('colors.ink.200'),
            '--tw-prose-quote-borders': theme('colors.ink.700'),
            '--tw-prose-captions': theme('colors.ink.400'),
            '--tw-prose-code': theme('colors.ink.100'),
            '--tw-prose-th-borders': theme('colors.ink.600'),
            '--tw-prose-td-borders': theme('colors.ink.700'),
            code: { backgroundColor: theme('colors.ink.800') },
          },
        },
      }),
    },
  },
  plugins: [typography],
} satisfies Config;
