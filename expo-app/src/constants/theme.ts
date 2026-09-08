/**
 * Aradhana Jewellers — Joylukkas-inspired premium design system.
 * Central design tokens. Never scatter hex values in screens.
 */

import '@/global.css';

import { Platform } from 'react-native';
import { MASTER, TAGLINE } from '@/config/master';

export const Colors = {
  light: {
    text: '#1A1A2E',
    textSecondary: '#6B7280',
    textMuted: '#9CA3AF',
    background: '#FFFFFF',
    backgroundWarm: '#FFFBF5',
    backgroundElement: '#F8F6F3',
    backgroundSelected: '#EDE8DF',
    backgroundGold: '#FDF8ED',
    primary: '#23519D',
    primaryDeep: '#173A75',
    primaryLight: '#E8EFFA',
    navy: '#1A1A2E',
    gold: '#C9A84C',
    goldDeep: '#A68523',
    goldLight: '#F5ECD7',
    goldMuted: '#E8D9A8',
    onPrimary: '#FFFFFF',
    cardBorder: '#E5E1D8',
    cardShadow: 'rgba(0,0,0,0.06)',
    up: '#16A34A',
    down: '#DC2626',
    divider: '#F0ECE4',
  },
  dark: {
    text: '#F5EFE2',
    textSecondary: '#9BA6BC',
    textMuted: '#6B7280',
    background: '#0A1220',
    backgroundWarm: '#0F1A2E',
    backgroundElement: '#13203A',
    backgroundSelected: '#1B2C4C',
    backgroundGold: '#1A1508',
    primary: '#5B84CE',
    primaryDeep: '#173A75',
    primaryLight: '#1B2C4C',
    navy: '#050D1D',
    gold: '#E2B84C',
    goldDeep: '#E2B84C',
    goldLight: '#2A2210',
    goldMuted: '#3D3018',
    onPrimary: '#FFFFFF',
    cardBorder: '#1B2C4C',
    cardShadow: 'rgba(0,0,0,0.3)',
    up: '#22C55E',
    down: '#EF4444',
    divider: '#1B2C4C',
  },
} as const;

export const Brand = {
  name: MASTER.displayName,
  tagline: TAGLINE,
  instagram: MASTER.instagram,
  whatsapp: MASTER.whatsapp,
  phone: MASTER.phone,
  showroom: MASTER.shortAddress,
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

/**
 * Premium font system — Joylukkas uses elegant serif headings with clean sans-serif body.
 * System serif on iOS (ui-serif), Playfair Display–like serif on Android.
 */
export const Fonts = Platform.select({
  ios: {
    sans: 'system-ui',
    serif: 'ui-serif',
    rounded: 'ui-rounded',
    mono: 'ui-monospace',
    headingSerif: 'ui-serif',
    display: 'system-ui',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
    headingSerif: 'serif',
    display: 'normal',
  },
  web: {
    sans: 'var(--font-display)',
    serif: 'var(--font-serif)',
    rounded: 'var(--font-rounded)',
    mono: 'var(--font-mono)',
    headingSerif: 'var(--font-serif)',
    display: 'var(--font-display)',
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
  eight: 80,
} as const;

export const BorderRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 28,
  full: 999,
} as const;

export const Shadow = Platform.select({
  ios: {
    sm: { shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 3 },
    md: { shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.08, shadowRadius: 8 },
    lg: { shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.12, shadowRadius: 16 },
  },
  default: {
    sm: { elevation: 1 },
    md: { elevation: 3 },
    lg: { elevation: 6 },
  },
});

export const BottomTabInset = Platform.select({ ios: 50, android: 80 }) ?? 0;
export const MaxContentWidth = 800;
