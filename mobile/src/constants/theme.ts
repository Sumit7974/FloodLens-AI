/**
 * FloodLens Mobile Tactical Theme & Design System Tokens
 * Aligned with the Authority Command Center web styling.
 */

export const THEME = {
  colors: {
    // Backgrounds
    darkBg: '#030712',
    cardBg: '#0b1329',
    cardBgHover: '#0f1d36',
    cardBorder: '#1e293b',
    cardBorderHighlight: '#38bdf8',

    // Tactical Accents
    cyan: '#06b6d4',
    sky: '#38bdf8',
    amber: '#f59e0b',
    rose: '#f43f5e',
    emerald: '#10b981',
    indigo: '#6366f1',
    purple: '#a855f7',

    // Text Elements
    textPrimary: '#f8fafc',
    textSecondary: '#94a3b8',
    textMuted: '#64748b',

    // Status Badges & Glows
    status: {
      success: {
        bg: 'rgba(16, 185, 129, 0.15)',
        border: 'rgba(16, 185, 129, 0.35)',
        text: '#34d399',
        dot: '#10b981',
      },
      warning: {
        bg: 'rgba(245, 158, 11, 0.15)',
        border: 'rgba(245, 158, 11, 0.35)',
        text: '#fbbf24',
        dot: '#f59e0b',
      },
      destructive: {
        bg: 'rgba(244, 63, 94, 0.15)',
        border: 'rgba(244, 63, 94, 0.35)',
        text: '#fda4af',
        dot: '#f43f5e',
      },
      info: {
        bg: 'rgba(6, 182, 212, 0.15)',
        border: 'rgba(6, 182, 212, 0.35)',
        text: '#38bdf8',
        dot: '#06b6d4',
      },
    },
  },
  typography: {
    headerSize: 18,
    cardTitleSize: 13,
    metricDisplaySize: 26,
    bodySize: 14,
    captionSize: 11,
    microSize: 10,
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,
    xxl: 24,
  },
  borderRadius: {
    sm: 6,
    md: 8,
    lg: 12,
    full: 9999,
  },
} as const;

export const DEFAULT_COORDINATES = {
  koshiBasin: {
    latitude: 26.8521,
    longitude: 87.1654,
    latitudeDelta: 0.25,
    longitudeDelta: 0.25,
    sectorName: 'NEPAL TERAI - KOSHI BASIN',
  },
} as const;

export default THEME;
