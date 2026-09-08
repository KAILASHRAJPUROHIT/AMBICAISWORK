/* eslint-disable react-hooks/immutability */
import { useCallback } from 'react';
import { Pressable, StyleSheet, View, type ViewStyle, type StyleProp } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  interpolate,
  Extrapolation,
} from 'react-native-reanimated';

import { ThemedText } from '@/components/themed-text';
import { SPRING, TIMING } from '@/components/animated-3d';
import { BorderRadius } from '@/constants/theme';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

/* ──────────────────────────────────────────────────────────
   Button3D — Premium 3D pressable button with depth
   ────────────────────────────────────────────────────────── */
type Button3DProps = {
  children: React.ReactNode;
  onPress?: () => void;
  variant?: 'primary' | 'secondary' | 'gold' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  icon?: string;
  style?: StyleProp<ViewStyle>;
  disabled?: boolean;
};

export function Button3D({
  children,
  onPress,
  variant = 'primary',
  size = 'md',
  icon,
  style,
  disabled,
}: Button3DProps) {
  const scale = useSharedValue(1);
  const translateY = useSharedValue(0);
  const depth = useSharedValue(4);

  const colors = {
    primary: { bg: '#23519D', shadow: '#173A75', text: '#FFFFFF' },
    secondary: { bg: '#FFFFFF', shadow: '#E5E1D8', text: '#1A1A2E' },
    gold: { bg: '#C9A84C', shadow: '#A68523', text: '#FFFFFF' },
    ghost: { bg: 'transparent', shadow: 'transparent', text: '#6B7280' },
  }[variant];

  const sizes = {
    sm: { paddingV: 8, paddingH: 16, fontSize: 12, radius: BorderRadius.sm },
    md: { paddingV: 12, paddingH: 20, fontSize: 14, radius: BorderRadius.md },
    lg: { paddingV: 16, paddingH: 24, fontSize: 16, radius: BorderRadius.lg },
  }[size];

  const animStyle = useAnimatedStyle(() => ({
    transform: [
      { scale: scale.value },
      { translateY: translateY.value },
    ],
    elevation: depth.value,
    shadowOpacity: variant !== 'ghost' ? interpolate(depth.value, [0, 8], [0.15, 0.3], Extrapolation.CLAMP) : 0,
  }));

  const onGrant = useCallback(() => {
    if (disabled) return;
    scale.value = withSpring(0.96, SPRING.snappy);
    translateY.value = withSpring(2, SPRING.snappy);
    depth.value = withSpring(0, SPRING.gentle);
  }, [scale, translateY, depth, disabled]);

  const onRelease = useCallback(() => {
    if (disabled) return;
    scale.value = withSpring(1, SPRING.bouncy);
    translateY.value = withSpring(0, SPRING.bouncy);
    depth.value = withSpring(4, SPRING.gentle);
  }, [scale, translateY, depth, disabled]);

  return (
    <AnimatedPressable
      onPress={onPress}
      onPressIn={onGrant}
      onPressOut={onRelease}
      disabled={disabled}
      style={[
        {
          backgroundColor: colors.bg,
          paddingVertical: sizes.paddingV,
          paddingHorizontal: sizes.paddingH,
          borderRadius: sizes.radius,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          shadowColor: colors.shadow,
          shadowOffset: { width: 0, height: 4 },
          shadowRadius: 8,
          opacity: disabled ? 0.5 : 1,
        },
        animStyle,
        style,
      ]}>
      {icon && <ThemedText style={{ fontSize: sizes.fontSize }}>{icon}</ThemedText>}
      <ThemedText style={{ color: colors.text, fontSize: sizes.fontSize, fontWeight: '700' }}>
        {children}
      </ThemedText>
    </AnimatedPressable>
  );
}

/* ──────────────────────────────────────────────────────────
   Chip3D — Animated filter chip
   ────────────────────────────────────────────────────────── */
type Chip3DProps = {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  count?: number;
};

export function Chip3D({ label, selected, onPress, count }: Chip3DProps) {
  const scale = useSharedValue(1);

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  return (
    <AnimatedPressable
      onPress={onPress}
      onPressIn={() => { scale.value = withSpring(0.92, SPRING.snappy); }}
      onPressOut={() => { scale.value = withSpring(1, SPRING.bouncy); }}
      style={[
        styles.chip,
        selected && styles.chipActive,
        animStyle,
      ]}>
      <ThemedText style={[styles.chipText, selected && styles.chipTextActive]}>
        {label}
      </ThemedText>
      {count !== undefined && (
        <View style={[styles.chipCount, selected && styles.chipCountActive]}>
          <ThemedText style={[styles.chipCountText, selected && styles.chipCountTextActive]}>
            {count}
          </ThemedText>
        </View>
      )}
    </AnimatedPressable>
  );
}

/* ──────────────────────────────────────────────────────────
   Badge3D — Animated notification badge with bounce
   ────────────────────────────────────────────────────────── */
type Badge3DProps = {
  count: number;
  color?: string;
};

export function Badge3D({ count, color = '#DC2626' }: Badge3DProps) {
  const scale = useSharedValue(0);

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  if (count > 0 && scale.value === 0) {
    scale.value = withSpring(1, SPRING.bouncy);
  }

  if (count === 0 && scale.value !== 0) {
    scale.value = withSpring(0, SPRING.snappy);
  }

  return (
    <Animated.View style={[styles.badge, { backgroundColor: color }, animStyle]}>
      <ThemedText style={styles.badgeText}>{count > 99 ? '99+' : count}</ThemedText>
    </Animated.View>
  );
}

/* ──────────────────────────────────────────────────────────
   Toggle3D — Animated toggle switch
   ────────────────────────────────────────────────────────── */
type Toggle3DProps = {
  value: boolean;
  onValueChange: (val: boolean) => void;
};

export function Toggle3D({ value, onValueChange }: Toggle3DProps) {
  const thumbX = useSharedValue(value ? 20 : 0);
  const activeOpacity = useSharedValue(value ? 1 : 0);

  const thumbStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: thumbX.value }],
  }));

  const activeStyle = useAnimatedStyle(() => ({
    opacity: activeOpacity.value,
  }));

  const inactiveStyle = useAnimatedStyle(() => ({
    opacity: 1 - activeOpacity.value,
  }));

  const toggle = useCallback(() => {
    const next = !value;
    thumbX.value = withSpring(next ? 20 : 0, SPRING.snappy);
    activeOpacity.value = withTiming(next ? 1 : 0, { duration: TIMING.fast });
    onValueChange(next);
  }, [value, thumbX, activeOpacity, onValueChange]);

  return (
    <AnimatedPressable onPress={toggle} style={[styles.toggle]}>
      <Animated.View style={[styles.toggleBgActive, activeStyle]} />
      <Animated.View style={[styles.toggleBgInactive, inactiveStyle]} />
      <Animated.View style={[styles.toggleThumb, thumbStyle]} />
    </AnimatedPressable>
  );
}

/* ──────────────────────────────────────────────────────────
   ProgressBar3D — Animated progress bar
   ────────────────────────────────────────────────────────── */
type ProgressBar3DProps = {
  progress: number; // 0-1
  color?: string;
  height?: number;
};

export function ProgressBar3D({
  progress,
  color = '#23519D',
  height = 8,
}: ProgressBar3DProps) {
  const width = useSharedValue(0);

  const barStyle = useAnimatedStyle(() => ({
    width: `${width.value * 100}%` as any,
  }));

  // Trigger animation on mount
  if (width.value === 0 && progress > 0) {
    width.value = withSpring(progress, SPRING.gentle);
  }

  return (
    <View style={[styles.progressTrack, { height, borderRadius: height / 2 }]}>
      <Animated.View
        style={[
          styles.progressFill,
          { backgroundColor: color, borderRadius: height / 2 },
          barStyle,
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  /* Chip */
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#F8F6F3',
    borderWidth: 1,
    borderColor: '#E5E1D8',
  },
  chipActive: {
    backgroundColor: '#23519D',
    borderColor: '#23519D',
  },
  chipText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#6B7280',
  },
  chipTextActive: {
    color: '#FFFFFF',
  },
  chipCount: {
    backgroundColor: '#E5E1D8',
    borderRadius: 10,
    minWidth: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  chipCountActive: {
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
  chipCountText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#6B7280',
  },
  chipCountTextActive: {
    color: '#FFFFFF',
  },

  /* Badge */
  badge: {
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '700',
  },

  /* Toggle */
  toggle: {
    width: 44,
    height: 24,
    borderRadius: 12,
    paddingHorizontal: 2,
    justifyContent: 'center',
    position: 'relative',
  },
  toggleBgActive: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 12,
    backgroundColor: '#23519D',
  },
  toggleBgInactive: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 12,
    backgroundColor: '#E5E1D8',
  },
  toggleThumb: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#FFFFFF',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
    elevation: 2,
  },

  /* Progress */
  progressTrack: {
    width: '100%',
    backgroundColor: '#F0ECE4',
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
  },
});
