/* eslint-disable react-hooks/immutability */
import { useCallback, useEffect, useRef } from 'react';
import { StyleProp, ViewStyle } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withRepeat,
  withSequence,
  withDelay,
  interpolate,
  Extrapolation,
  type SharedValue,
} from 'react-native-reanimated';

// eslint-disable-next-line @typescript-eslint/no-require-imports
const AnimatedTouchable = Animated.createAnimatedComponent(require('react-native').Pressable);

/* ──────────────────────────────────────────────────────────
   SPRING CONFIGS — tuned for jewellery-premium feel
   ────────────────────────────────────────────────────────── */
export const SPRING = {
  snappy: { damping: 15, stiffness: 180, mass: 0.8 },
  gentle: { damping: 20, stiffness: 120, mass: 1 },
  bouncy: { damping: 10, stiffness: 150, mass: 0.6 },
  stiff: { damping: 25, stiffness: 300, mass: 0.5 },
} as const;

export const TIMING = {
  fast: 150,
  normal: 250,
  slow: 400,
  reveal: 600,
} as const;

/* ──────────────────────────────────────────────────────────
   use3DTilt — Interactive 3D tilt on press/hover
   ────────────────────────────────────────────────────────── */
export function use3DTilt(intensity: number = 12) {
  const rotateX = useSharedValue(0);
  const rotateY = useSharedValue(0);
  const scale = useSharedValue(1);
  const elevation = useSharedValue(0);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { perspective: 800 },
      { scale: scale.value },
      { rotateX: `${rotateX.value}deg` },
      { rotateY: `${rotateY.value}deg` },
    ],
    elevation: elevation.value,
    shadowOpacity: interpolate(elevation.value, [0, 12], [0.06, 0.25], Extrapolation.CLAMP),
  }));

  const onGrant = useCallback(() => {
    scale.value = withSpring(1.03, SPRING.snappy);
    elevation.value = withSpring(8, SPRING.gentle);
  }, [scale, elevation]);

  const onMove = useCallback(
    (evt: any) => {
      const { locationX, locationY } = evt.nativeEvent;
      const centerX = locationX || 0;
      const centerY = locationY || 0;
      rotateY.value = withSpring(
        ((centerX - 50) / 50) * intensity,
        SPRING.gentle,
      );
      rotateX.value = withSpring(
        -((centerY - 50) / 50) * intensity,
        SPRING.gentle,
      );
    },
    [rotateX, rotateY, intensity],
  );

  const onRelease = useCallback(() => {
    rotateX.value = withSpring(0, SPRING.snappy);
    rotateY.value = withSpring(0, SPRING.snappy);
    scale.value = withSpring(1, SPRING.snappy);
    elevation.value = withSpring(0, SPRING.gentle);
  }, [rotateX, rotateY, scale, elevation]);

  return { animatedStyle, onGrant, onMove, onRelease };
}

/* ──────────────────────────────────────────────────────────
   usePressScale — Simple press-to-scale animation
   ────────────────────────────────────────────────────────── */
export function usePressScale(pressScale: number = 0.96) {
  const scale = useSharedValue(1);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const onGrant = useCallback(() => {
    scale.value = withSpring(pressScale, SPRING.snappy);
  }, [scale, pressScale]);

  const onRelease = useCallback(() => {
    scale.value = withSpring(1, SPRING.bouncy);
  }, [scale]);

  return { animatedStyle, onGrant, onRelease };
}

/* ──────────────────────────────────────────────────────────
   useGlow — Pulsing gold glow animation
   ────────────────────────────────────────────────────────── */
export function useGlow(color: string = '#C9A84C') {
  const glowOpacity = useSharedValue(0);

  const animatedStyle = useAnimatedStyle(() => ({
    shadowColor: color,
    shadowOpacity: glowOpacity.value,
    shadowRadius: interpolate(glowOpacity.value, [0, 1], [0, 20], Extrapolation.CLAMP),
    elevation: interpolate(glowOpacity.value, [0, 1], [0, 12], Extrapolation.CLAMP),
  }));

  const startGlow = useCallback(() => {
    glowOpacity.value = withRepeat(
      withSequence(
        withTiming(0.6, { duration: 1200 }),
        withTiming(0.15, { duration: 1200 }),
      ),
      -1,
      true,
    );
  }, [glowOpacity]);

  const stopGlow = useCallback(() => {
    glowOpacity.value = withTiming(0, { duration: 300 });
  }, [glowOpacity]);

  return { animatedStyle, startGlow, stopGlow };
}

/* ──────────────────────────────────────────────────────────
   useSlideReveal — Slide + fade reveal animation
   ────────────────────────────────────────────────────────── */
export function useSlideReveal(
  direction: 'up' | 'down' | 'left' | 'right' = 'up',
  delay: number = 0,
) {
  const progress = useSharedValue(0);

  const getTranslate = () => {
    const distance = 40;
    switch (direction) {
      case 'up': return { translateX: 0, translateY: distance };
      case 'down': return { translateX: 0, translateY: -distance };
      case 'left': return { translateX: distance, translateY: 0 };
      case 'right': return { translateX: -distance, translateY: 0 };
    }
  };

  const { translateX, translateY } = getTranslate();

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: progress.value,
    transform: [
      { translateX: interpolate(progress.value, [0, 1], [translateX, 0], Extrapolation.CLAMP) },
      { translateY: interpolate(progress.value, [0, 1], [translateY, 0], Extrapolation.CLAMP) },
    ],
  }));

  const trigger = useCallback(() => {
    progress.value = withDelay(delay, withTiming(1, { duration: TIMING.reveal }));
  }, [progress, delay]);

  return { animatedStyle, trigger, progress };
}

/* ──────────────────────────────────────────────────────────
   useParallax — Scroll-driven parallax effect
   ────────────────────────────────────────────────────────── */
export function useParallax(scrollY: SharedValue<number>, speed: number = 0.5) {
  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: interpolate(scrollY.value, [0, 500], [0, -100 * speed], Extrapolation.CLAMP) },
    ],
  }));

  return { animatedStyle };
}

/* ──────────────────────────────────────────────────────────
   use3DRotate — Continuous slow 3D rotation
   ────────────────────────────────────────────────────────── */
export function use3DRotate(axis: 'X' | 'Y' | 'Z' = 'Y', speed: number = 8000) {
  const rotation = useSharedValue(0);

  const animatedStyle = useAnimatedStyle(() => {
    const angle = `${rotation.value}deg`;

    if (axis === 'X') return { transform: [{ perspective: 600 }, { rotateX: angle }] };
    if (axis === 'Z') return { transform: [{ perspective: 600 }, { rotateZ: angle }] };

    return { transform: [{ perspective: 600 }, { rotateY: angle }] };
  });

  const start = useCallback(() => {
    rotation.value = withRepeat(
      withTiming(360, { duration: speed }),
      -1,
      false,
    );
  }, [rotation, speed]);

  const stop = useCallback(() => {
    rotation.value = withTiming(0, { duration: 500 });
  }, [rotation]);

  return { animatedStyle, start, stop };
}

/* ──────────────────────────────────────────────────────────
   useMorph — Morph between two visual states
   ────────────────────────────────────────────────────────── */
export function useMorph() {
  const progress = useSharedValue(0);

  const animatedStyle = useAnimatedStyle(() => ({
    borderRadius: interpolate(progress.value, [0, 1], [8, 24], Extrapolation.CLAMP),
    backgroundColor: progress.value > 0.5 ? '#23519D' : '#FFFFFF',
  }));

  const morphIn = useCallback(() => {
    progress.value = withSpring(1, SPRING.gentle);
  }, [progress]);

  const morphOut = useCallback(() => {
    progress.value = withSpring(0, SPRING.gentle);
  }, [progress]);

  return { animatedStyle, morphIn, morphOut, progress };
}

/* ──────────────────────────────────────────────────────────
   Reusable Animated Components
   ────────────────────────────────────────────────────────── */

type Card3DProps = {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
  tilt?: number;
  glowColor?: string;
};

export function Card3D({ children, style, onPress, tilt = 8, glowColor }: Card3DProps) {
  const tiltAnim = use3DTilt(tilt);
  const glow = useGlow(glowColor);

  return (
    <AnimatedTouchable
      onPress={onPress}
      onPressIn={() => {
        tiltAnim.onGrant();
        if (glowColor) glow.startGlow();
      }}
      onPressMove={tiltAnim.onMove}
      onPressOut={() => {
        tiltAnim.onRelease();
        if (glowColor) glow.stopGlow();
      }}
      style={[tiltAnim.animatedStyle, glowColor ? glow.animatedStyle : undefined, style]}>
      {children}
    </AnimatedTouchable>
  );
}

type RevealProps = {
  children: React.ReactNode;
  direction?: 'up' | 'down' | 'left' | 'right';
  delay?: number;
  style?: StyleProp<ViewStyle>;
};

export function RevealOnMount({ children, direction = 'up', delay = 0, style }: RevealProps) {
  const reveal = useSlideReveal(direction, delay);
  const mounted = useRef(false);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      reveal.trigger();
    }
  }, [reveal]);

  return (
    <Animated.View style={[reveal.animatedStyle, style]}>
      {children}
    </Animated.View>
  );
}

type GlowBadgeProps = {
  children: React.ReactNode;
  color?: string;
  style?: StyleProp<ViewStyle>;
};

export function GlowBadge({ children, color = '#C9A84C', style }: GlowBadgeProps) {
  const glow = useGlow(color);

  return (
    <Animated.View style={[glow.animatedStyle, style]}>
      {children}
    </Animated.View>
  );
}

type FloatingProps = {
  children: React.ReactNode;
  amplitude?: number;
  speed?: number;
  style?: StyleProp<ViewStyle>;
};

export function Floating({ children, amplitude = 6, speed = 3000, style }: FloatingProps) {
  const floatY = useSharedValue(0);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: floatY.value }],
  }));

  useEffect(() => {
    floatY.value = withRepeat(
      withSequence(
        withTiming(-amplitude, { duration: speed / 2 }),
        withTiming(amplitude, { duration: speed / 2 }),
      ),
      -1,
      true,
    );
  }, [floatY, amplitude, speed]);

  return (
    <Animated.View style={[animatedStyle, style]}>
      {children}
    </Animated.View>
  );
}
