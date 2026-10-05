// Low-battery stages, the same rules the tablets use: 31%+ normal, 21-30% yellow, 11-20% orange, 10% and below red.
export type BatteryStage = 'ok' | 'yellow' | 'orange' | 'red';

export function batteryStage(percent: number | null | undefined, charging?: boolean): BatteryStage {
  if (percent == null || percent < 0 || charging) return 'ok';
  if (percent > 30) return 'ok';
  if (percent > 20) return 'yellow';
  if (percent > 10) return 'orange';
  return 'red';
}

/** Class name used by the battery bars and rings (red keeps the existing "fail" look). */
export function batteryClass(percent: number | null | undefined, charging?: boolean): string {
  const s = batteryStage(percent, charging);
  return s === 'ok' ? 'ok' : s === 'red' ? 'fail' : `bat-${s}`;
}

export const BATTERY_TEXT_COLOR: Record<BatteryStage, string | undefined> = {
  ok: undefined,
  yellow: '#d9a40f',
  orange: '#e07b17',
  red: '#d6393e',
};
