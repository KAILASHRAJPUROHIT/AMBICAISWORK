import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  ActivityIndicator,
  Animated,
  Dimensions,
  PanResponder,
  Pressable,
  Share,
  StyleSheet,
  View,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BorderRadius } from '@/constants/theme';
import { analytics } from '@/services/analytics';
import { getById } from '@/services/products';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');
const RING_SIZE = 80;
const TUTORIAL_SEEN_KEY = 'ar_tutorial_seen';

/* ── Ring Sizes (India standard) ───────────────────────────────────────── */
const RING_SIZES = [
  { size: '6', diameter_mm: 16.5, label: 'XS' },
  { size: '7', diameter_mm: 17.3, label: 'S' },
  { size: '8', diameter_mm: 18.1, label: 'M' },
  { size: '9', diameter_mm: 18.9, label: 'L' },
  { size: '10', diameter_mm: 19.8, label: 'XL' },
  { size: '11', diameter_mm: 20.6, label: 'XXL' },
  { size: '12', diameter_mm: 21.4, label: '3XL' },
  { size: '13', diameter_mm: 22.2, label: '4XL' },
] as const;

/* ── Metal Color Map ───────────────────────────────────────────────────── */
const METAL_COLORS: Record<string, { band: string; highlight: string; shadow: string }> = {
  yellow: { band: '#D4A843', highlight: '#F5E6B8', shadow: '#A68523' },
  rose: { band: '#C9A087', highlight: '#F0D5C8', shadow: '#9C7A63' },
  white: { band: '#E8E8E8', highlight: '#FFFFFF', shadow: '#B8B8B8' },
};

export default function ARScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    productId?: string;
    variantId?: string;
    karat?: string;
  }>();

  const [permission, requestPermission] = useCameraPermissions();
  const [ringPos, setRingPos] = useState({ x: SCREEN_W / 2 - RING_SIZE / 2, y: SCREEN_H * 0.6 });
  const [ringScale, setRingScale] = useState(1.0);
  const [showTutorial, setShowTutorial] = useState(false);
  const [showSizeGuide, setShowSizeGuide] = useState(false);
  const [selectedSize, setSelectedSize] = useState<typeof RING_SIZES[number] | null>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const cameraRef = useRef<React.ElementRef<typeof CameraView>>(null);
  const lastTap = useRef(0);

  // Animated values for pan gesture - use useState to satisfy linter
  const [panAnimX] = useState(() => new Animated.Value(0));
  const [panAnimY] = useState(() => new Animated.Value(0));

  // Resolve product from params
  const product = params.productId ? getById(params.productId) : undefined;
  const variant = params.variantId
    ? product?.threeD?.materialVariants.find((v) => v.id === params.variantId) ?? null
    : null;
  const karat = params.karat ? parseInt(params.karat, 10) : product?.karat ?? 22;

  const metalColor = variant?.metalColor ?? 'yellow';
  const metalTheme = METAL_COLORS[metalColor] ?? METAL_COLORS.yellow;

  // Check if first time user
  useEffect(() => {
    AsyncStorage.getItem(TUTORIAL_SEEN_KEY).then((seen) => {
      if (!seen) setShowTutorial(true);
    });
  }, []);

  useEffect(() => {
    analytics.track('ar_session_started', { productId: product?.id });
    return () => { analytics.track('ar_session_ended', { productId: product?.id }); };
  }, [product?.id]);

  const dismissTutorial = useCallback(() => {
    setShowTutorial(false);
    AsyncStorage.setItem(TUTORIAL_SEEN_KEY, 'true');
  }, []);

  // ── PanResponder for drag ──
  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: (_, gestureState) =>
          Math.abs(gestureState.dx) > 2 || Math.abs(gestureState.dy) > 2,
        onPanResponderGrant: () => {
          panAnimX.setOffset(0);
          panAnimY.setOffset(0);
          panAnimX.setValue(0);
          panAnimY.setValue(0);
        },
        onPanResponderMove: Animated.event(
          [null, { dx: panAnimX, dy: panAnimY }],
          { useNativeDriver: false }
        ),
        onPanResponderRelease: (_, gestureState) => {
          panAnimX.flattenOffset();
          panAnimY.flattenOffset();

          setRingPos((prev) => ({
            x: Math.max(0, Math.min(SCREEN_W - RING_SIZE, prev.x + gestureState.dx)),
            y: Math.max(100, Math.min(SCREEN_H - RING_SIZE - 120, prev.y + gestureState.dy)),
          }));
          panAnimX.setValue(0);
          panAnimY.setValue(0);
        },
      }),
    [panAnimX, panAnimY]
  );

  // ── Double tap to reset ──
  const handleDoubleTap = useCallback(() => {
    const now = Date.now();
    if (now - lastTap.current < 300) {
      setRingPos({ x: SCREEN_W / 2 - RING_SIZE / 2, y: SCREEN_H * 0.6 });
      setRingScale(1.0);
      panAnimX.setValue(0);
      panAnimY.setValue(0);
    }
    lastTap.current = now;
  }, [panAnimX, panAnimY]);

  // CameraView captures the camera feed. The React Native overlay is not part of this photo.
  const shareCameraPhoto = useCallback(async () => {
    if (!cameraRef.current || isCapturing) return;
    setIsCapturing(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.9 });
      await Share.share({
        url: photo.uri,
        message: `Camera preview from Aradhana Jewellers — ${product?.categoryName ?? ''} ${product?.label ?? ''}`.trim(),
      });
      analytics.track('ar_camera_photo_shared', { productId: product?.id });
    } catch {
      // User cancelled share or capture failed
    } finally {
      setIsCapturing(false);
    }
  }, [isCapturing, product]);

  // ── Permission states ──
  if (!permission) {
    return (
      <ThemedView style={styles.center}>
        <ActivityIndicator size="large" color="#C9A84C" />
      </ThemedView>
    );
  }

  if (!permission.granted) {
    return (
      <ThemedView style={styles.center}>
        <SafeAreaView style={styles.center}>
          <ThemedText style={styles.permTitle}>Camera Access Needed</ThemedText>
          <ThemedText style={styles.permDesc}>
            To try on rings virtually, we need access to your camera.{'\n\n'}
            Camera data stays on your device and is never stored or shared.
          </ThemedText>
          <Pressable onPress={requestPermission} style={styles.permBtn}>
            <ThemedText style={styles.permBtnText}>Enable Camera</ThemedText>
          </Pressable>
          <Pressable onPress={() => router.back()} style={styles.permBackBtn}>
            <ThemedText style={styles.permBackBtnText}>Go Back</ThemedText>
          </Pressable>
        </SafeAreaView>
      </ThemedView>
    );
  }

  return (
    <View style={styles.container}>
      {/* Camera Feed */}
      <CameraView ref={cameraRef} style={styles.camera} facing="back">
        {/* Draggable Ring Overlay */}
        <Animated.View
          {...panResponder.panHandlers}
          style={[
            styles.ringOverlay,
            {
              left: Animated.add(ringPos.x, panAnimX),
              top: Animated.add(ringPos.y, panAnimY),
              transform: [{ scale: ringScale }],
            },
          ]}
          onTouchEnd={handleDoubleTap}
          accessibilityLabel="Ring overlay — drag to reposition, double tap to reset"
        >
          <View style={styles.ringGraphic}>
            {/* Outer glow */}
            <View style={[styles.ringGlow, { backgroundColor: metalTheme.highlight + '40' }]} />
            {/* Gold band */}
            <View
              style={[
                styles.ringBand,
                {
                  borderColor: metalTheme.band,
                  shadowColor: metalTheme.shadow,
                },
              ]}
            />
            {/* Inner highlight */}
            <View
              style={[
                styles.ringHighlight,
                {
                  borderColor: metalTheme.highlight,
                  backgroundColor: metalTheme.band + '15',
                },
              ]}
            />
            {/* Stone */}
            {product?.threeD?.stones && product.threeD.stones.length > 0 ? (
              <View style={styles.stoneContainer}>
                <View style={[styles.stoneMain, { backgroundColor: '#FFFFFF', borderColor: '#E8E8E8' }]} />
                <View style={styles.stoneSparkle} />
              </View>
            ) : (
              <View style={[styles.stoneSimple, { backgroundColor: metalTheme.band }]} />
            )}
          </View>

          {/* Product label */}
          {product && (
            <View style={styles.ringLabel}>
              <ThemedText style={styles.ringLabelText} numberOfLines={1}>
                {product.label}
              </ThemedText>
              {karat && <ThemedText style={styles.ringLabelKarat}>{karat}K</ThemedText>}
            </View>
          )}
        </Animated.View>

        {/* Disclaimer */}
        <View style={styles.disclaimerBar}>
          <ThemedText style={styles.disclaimerText}>
            Visual approximation only. Actual appearance may vary.
          </ThemedText>
        </View>

        {/* Top Controls */}
        <View style={styles.topControls}>
          <Pressable onPress={() => router.back()} style={styles.topBtn} accessibilityLabel="Close">
            <ThemedText style={styles.topBtnText}>{'\u2715'}</ThemedText>
          </Pressable>
          <ThemedText style={styles.topTitle}>AR Try-On</ThemedText>
          <Pressable
            onPress={() => setShowSizeGuide(true)}
            style={styles.topBtn}
            accessibilityLabel="Ring size guide"
          >
            <ThemedText style={styles.topBtnText}>{'\u24D8'}</ThemedText>
          </Pressable>
        </View>

        {/* Bottom Controls */}
        <View style={styles.controls}>
          <Pressable
            onPress={() => setRingScale((s) => Math.max(0.5, s - 0.1))}
            style={styles.controlBtn}
            accessibilityLabel="Smaller ring"
          >
            <ThemedText style={styles.controlBtnText}>{'\u2212'}</ThemedText>
          </Pressable>

          <Pressable
            onPress={shareCameraPhoto}
            style={[styles.controlBtn, styles.captureBtn, isCapturing && styles.captureBtnDisabled]}
            disabled={isCapturing}
            accessibilityLabel="Capture and share camera photo"
          >
            {isCapturing ? (
              <ActivityIndicator size="small" color="#FFFFFF" />
            ) : (
              <ThemedText style={styles.captureBtnIcon}>{'\uD83D\uDCF7'}</ThemedText>
            )}
          </Pressable>

          <Pressable
            onPress={() => setRingScale((s) => Math.min(2.0, s + 0.1))}
            style={styles.controlBtn}
            accessibilityLabel="Larger ring"
          >
            <ThemedText style={styles.controlBtnText}>{'+'}</ThemedText>
          </Pressable>
        </View>

        {/* Size Guide Hint */}
        {selectedSize && (
          <View style={styles.sizeHint}>
            <ThemedText style={styles.sizeHintText}>
              Size {selectedSize.size} ({selectedSize.label}) — {selectedSize.diameter_mm}mm
            </ThemedText>
          </View>
        )}

        {/* ── Onboarding Tutorial ── */}
        {showTutorial && (
          <View style={styles.tutorialOverlay}>
            <View style={styles.tutorialCard}>
              <ThemedText style={styles.tutorialTitle}>How to Try On</ThemedText>
              <View style={styles.tutorialSteps}>
                <View style={styles.tutorialStep}>
                  <View style={styles.tutorialStepNum}><ThemedText style={styles.tutorialStepNumText}>1</ThemedText></View>
                  <ThemedText style={styles.tutorialStepText}>Point camera at your hand</ThemedText>
                </View>
                <View style={styles.tutorialStep}>
                  <View style={styles.tutorialStepNum}><ThemedText style={styles.tutorialStepNumText}>2</ThemedText></View>
                  <ThemedText style={styles.tutorialStepText}>Drag the ring to your finger</ThemedText>
                </View>
                <View style={styles.tutorialStep}>
                  <View style={styles.tutorialStepNum}><ThemedText style={styles.tutorialStepNumText}>3</ThemedText></View>
                  <ThemedText style={styles.tutorialStepText}>Pinch to resize, double-tap to reset</ThemedText>
                </View>
                <View style={styles.tutorialStep}>
                  <View style={styles.tutorialStepNum}><ThemedText style={styles.tutorialStepNumText}>4</ThemedText></View>
                  <ThemedText style={styles.tutorialStepText}>Tap camera icon to share a camera photo</ThemedText>
                </View>
              </View>
              <Pressable onPress={dismissTutorial} style={styles.tutorialBtn}>
                <ThemedText style={styles.tutorialBtnText}>Got it</ThemedText>
              </Pressable>
            </View>
          </View>
        )}

        {/* ── Size Guide Modal ── */}
        {showSizeGuide && (
          <View style={styles.sizeGuideOverlay}>
            <Pressable style={styles.sizeGuideBackdrop} onPress={() => setShowSizeGuide(false)} />
            <View style={styles.sizeGuideCard}>
              <View style={styles.sizeGuideHeader}>
                <ThemedText style={styles.sizeGuideTitle}>Ring Size Guide</ThemedText>
                <Pressable onPress={() => setShowSizeGuide(false)} accessibilityLabel="Close size guide">
                  <ThemedText style={styles.sizeGuideClose}>{'\u2715'}</ThemedText>
                </Pressable>
              </View>
              <ThemedText style={styles.sizeGuideSubtitle}>
                Tap your size to see a preview circle on camera
              </ThemedText>
              <View style={styles.sizeGrid}>
                {RING_SIZES.map((s) => (
                  <Pressable
                    key={s.size}
                    onPress={() => {
                      setSelectedSize(selectedSize?.size === s.size ? null : s);
                      const baseScale = 1.0;
                      const adjustedScale = baseScale * (s.diameter_mm / 18.1);
                      setRingScale(Math.max(0.5, Math.min(2.0, adjustedScale)));
                    }}
                    style={[
                      styles.sizeChip,
                      selectedSize?.size === s.size && styles.sizeChipActive,
                    ]}
                  >
                    <ThemedText
                      style={[
                        styles.sizeChipText,
                        selectedSize?.size === s.size && styles.sizeChipTextActive,
                      ]}
                    >
                      {s.size}
                    </ThemedText>
                    <ThemedText
                      style={[
                        styles.sizeChipLabel,
                        selectedSize?.size === s.size && styles.sizeChipLabelActive,
                      ]}
                    >
                      {s.label}
                    </ThemedText>
                  </Pressable>
                ))}
              </View>
              {selectedSize && (
                <View style={styles.sizePreview}>
                  <View
                    style={[
                      styles.sizePreviewCircle,
                      {
                        width: selectedSize.diameter_mm * 4,
                        height: selectedSize.diameter_mm * 4,
                        borderRadius: (selectedSize.diameter_mm * 4) / 2,
                      },
                    ]}
                  />
                  <ThemedText style={styles.sizePreviewText}>
                    {selectedSize.diameter_mm}mm inner diameter
                  </ThemedText>
                </View>
              )}
              <ThemedText style={styles.sizeGuideNote}>
                Tip: Measure an existing ring that fits well, or visit our store for professional sizing.
              </ThemedText>
            </View>
          </View>
        )}
      </CameraView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000000' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#FFFBF5', gap: 12, padding: 24 },

  /* Camera */
  camera: { flex: 1 },

  /* Ring Overlay */
  ringOverlay: {
    position: 'absolute',
    width: RING_SIZE,
    height: RING_SIZE,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ringGraphic: {
    width: RING_SIZE,
    height: RING_SIZE,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ringGlow: {
    position: 'absolute',
    width: RING_SIZE + 16,
    height: RING_SIZE + 16,
    borderRadius: (RING_SIZE + 16) / 2,
  },
  ringBand: {
    width: RING_SIZE,
    height: RING_SIZE,
    borderRadius: RING_SIZE / 2,
    borderWidth: 5,
    backgroundColor: 'transparent',
    position: 'absolute',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.4,
    shadowRadius: 6,
    elevation: 8,
  },
  ringHighlight: {
    width: RING_SIZE - 10,
    height: RING_SIZE - 10,
    borderRadius: (RING_SIZE - 10) / 2,
    borderWidth: 2,
    position: 'absolute',
  },
  stoneContainer: {
    position: 'absolute',
    top: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stoneMain: {
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 1,
  },
  stoneSparkle: {
    position: 'absolute',
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#FFFFFF',
    top: 1,
    left: 3,
  },
  stoneSimple: {
    position: 'absolute',
    top: 8,
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  ringLabel: {
    position: 'absolute',
    bottom: -24,
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.6)',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    minWidth: 80,
  },
  ringLabelText: { color: '#FFFFFF', fontSize: 10, fontWeight: '600', maxWidth: 100 },
  ringLabelKarat: { color: '#C9A84C', fontSize: 9, fontWeight: '700' },

  /* Disclaimer */
  disclaimerBar: {
    position: 'absolute',
    bottom: 110,
    left: 16,
    right: 16,
    backgroundColor: 'rgba(0,0,0,0.7)',
    borderRadius: BorderRadius.md,
    paddingVertical: 8,
    paddingHorizontal: 12,
    alignItems: 'center',
  },
  disclaimerText: { color: '#FFFFFF', fontSize: 11, textAlign: 'center' },

  /* Top Controls */
  topControls: {
    position: 'absolute',
    top: 50,
    left: 16,
    right: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  topBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.5)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  topBtnText: { color: '#FFFFFF', fontSize: 18, fontWeight: '600' },
  topTitle: { color: '#FFFFFF', fontSize: 16, fontWeight: '700' },

  /* Bottom Controls */
  controls: {
    position: 'absolute',
    bottom: 40,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 20,
  },
  controlBtn: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: 'rgba(255,255,255,0.9)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  controlBtnText: { fontSize: 22, fontWeight: '700', color: '#1A1A2E' },
  captureBtn: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#23519D',
    borderWidth: 3,
    borderColor: '#FFFFFF',
  },
  captureBtnDisabled: { opacity: 0.6 },
  captureBtnIcon: { fontSize: 24, color: '#FFFFFF' },

  /* Size Hint */
  sizeHint: {
    position: 'absolute',
    bottom: 108,
    alignSelf: 'center',
    backgroundColor: 'rgba(35,81,157,0.9)',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  sizeHintText: { color: '#FFFFFF', fontSize: 11, fontWeight: '600' },

  /* Permission */
  permTitle: { fontSize: 20, fontWeight: '700', color: '#1A1A2E', textAlign: 'center' },
  permDesc: { fontSize: 14, color: '#6B7280', textAlign: 'center', lineHeight: 20 },
  permBtn: { backgroundColor: '#23519D', borderRadius: 12, paddingHorizontal: 32, paddingVertical: 12, marginTop: 16 },
  permBtnText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
  permBackBtn: { marginTop: 12 },
  permBackBtnText: { color: '#6B7280', fontSize: 14 },

  /* Tutorial Overlay */
  tutorialOverlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0,0,0,0.85)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  tutorialCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: BorderRadius.xl,
    padding: 28,
    width: '100%',
    maxWidth: 360,
    gap: 20,
  },
  tutorialTitle: { fontSize: 22, fontWeight: '800', color: '#1A1A2E', textAlign: 'center' },
  tutorialSteps: { gap: 14 },
  tutorialStep: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  tutorialStepNum: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#23519D',
    alignItems: 'center',
    justifyContent: 'center',
  },
  tutorialStepNumText: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },
  tutorialStepText: { flex: 1, fontSize: 14, color: '#1A1A2E', lineHeight: 20 },
  tutorialBtn: {
    backgroundColor: '#23519D',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  tutorialBtnText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },

  /* Size Guide */
  sizeGuideOverlay: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'flex-end',
  },
  sizeGuideBackdrop: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  sizeGuideCard: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: BorderRadius.xxl,
    borderTopRightRadius: BorderRadius.xxl,
    padding: 24,
    paddingBottom: 40,
    gap: 16,
  },
  sizeGuideHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  sizeGuideTitle: { fontSize: 20, fontWeight: '700', color: '#1A1A2E' },
  sizeGuideClose: { fontSize: 20, color: '#6B7280', fontWeight: '600' },
  sizeGuideSubtitle: { fontSize: 13, color: '#6B7280' },
  sizeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  sizeChip: {
    width: 68,
    alignItems: 'center',
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: '#E5E1D8',
    backgroundColor: '#FFFFFF',
  },
  sizeChipActive: { borderColor: '#23519D', backgroundColor: '#EEF2FF' },
  sizeChipText: { fontSize: 16, fontWeight: '700', color: '#1A1A2E' },
  sizeChipTextActive: { color: '#23519D' },
  sizeChipLabel: { fontSize: 9, color: '#9CA3AF', fontWeight: '600', marginTop: 2 },
  sizeChipLabelActive: { color: '#23519D' },
  sizePreview: { alignItems: 'center', gap: 8, paddingVertical: 12 },
  sizePreviewCircle: {
    borderWidth: 3,
    borderColor: '#C9A84C',
    backgroundColor: 'rgba(201,168,76,0.08)',
  },
  sizePreviewText: { fontSize: 12, color: '#6B7280' },
  sizeGuideNote: { fontSize: 11, color: '#9CA3AF', textAlign: 'center', lineHeight: 16 },
});
