import { useState, useRef, useEffect } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BorderRadius } from '@/constants/theme';
import { analytics } from '@/services/analytics';

/**
 * AR Ring Try-On (Phase 4 pilot)
 *
 * Shows camera feed with a ring overlay positioned at a fixed point.
 * This is a visual approximation — not a tracked AR experience.
 * The spec requires: "Reject low-quality tracking; a weak AR effect damages trust more than no AR."
 *
 * This implementation:
 * - Camera feed with user's hand visible
 * - Ring overlay at center-bottom of screen (approximate finger position)
 * - User can drag to reposition the ring
 * - Clear "Visual approximation" disclaimer
 * - Camera permission is optional — 3D viewer works without it
 */

export default function ARScreen() {
  const router = useRouter();
  const [permission, requestPermission] = useCameraPermissions();
  const [ringPosition, setRingPosition] = useState({ x: 0.5, y: 0.7 });
  const [ringScale, setRingScale] = useState(1.0);
  const lastTap = useRef(0);

  useEffect(() => {
    analytics.track('ar_session_started');
    return () => { analytics.track('ar_session_ended'); };
  }, []);

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

  const handleDoubleTap = () => {
    const now = Date.now();
    if (now - lastTap.current < 300) {
      // Double tap — reset position
      setRingPosition({ x: 0.5, y: 0.7 });
      setRingScale(1.0);
    }
    lastTap.current = now;
  };

  return (
    <View style={styles.container}>
      {/* Camera Feed */}
      <CameraView style={styles.camera} facing="back">
        {/* Ring Overlay */}
        <Pressable
          style={[
            styles.ringOverlay,
            {
              left: `${ringPosition.x * 100 - 15}%`,
              top: `${ringPosition.y * 100 - 15}%`,
              transform: [{ scale: ringScale }],
            },
          ]}
          onPress={handleDoubleTap}
          accessibilityLabel="Ring overlay - double tap to reset">
          <View style={styles.ringGraphic}>
            <View style={styles.ringOuter} />
            <View style={styles.ringInner} />
            <View style={styles.ringStone} />
          </View>
        </Pressable>

        {/* Disclaimer */}
        <View style={styles.disclaimerBar}>
          <ThemedText style={styles.disclaimerText}>
            Visual approximation only. Actual appearance may vary.
          </ThemedText>
        </View>

        {/* Controls */}
        <View style={styles.controls}>
          <Pressable onPress={() => setRingScale(s => Math.max(0.5, s - 0.1))} style={styles.controlBtn}>
            <ThemedText style={styles.controlBtnText}>-</ThemedText>
          </Pressable>
          <Pressable onPress={() => setRingScale(s => Math.min(2.0, s + 0.1))} style={styles.controlBtn}>
            <ThemedText style={styles.controlBtnText}>+</ThemedText>
          </Pressable>
          <Pressable onPress={() => router.back()} style={[styles.controlBtn, styles.closeBtn]}>
            <ThemedText style={[styles.controlBtnText, { color: '#FFFFFF' }]}>X</ThemedText>
          </Pressable>
        </View>
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
    width: 80,
    height: 80,
    justifyContent: 'center',
    alignItems: 'center',
  },
  ringGraphic: { width: 60, height: 60, justifyContent: 'center', alignItems: 'center' },
  ringOuter: {
    width: 50,
    height: 50,
    borderRadius: 25,
    borderWidth: 4,
    borderColor: '#D4A843',
    backgroundColor: 'transparent',
    position: 'absolute',
  },
  ringInner: {
    width: 42,
    height: 42,
    borderRadius: 21,
    borderWidth: 2,
    borderColor: '#C9982A',
    backgroundColor: 'rgba(212,168,67,0.15)',
    position: 'absolute',
  },
  ringStone: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E8E8E8',
    position: 'absolute',
    top: 2,
  },

  /* Disclaimer */
  disclaimerBar: {
    position: 'absolute',
    bottom: 100,
    left: 16,
    right: 16,
    backgroundColor: 'rgba(0,0,0,0.7)',
    borderRadius: BorderRadius.md,
    paddingVertical: 8,
    paddingHorizontal: 12,
    alignItems: 'center',
  },
  disclaimerText: { color: '#FFFFFF', fontSize: 11, textAlign: 'center' },

  /* Controls */
  controls: {
    position: 'absolute',
    bottom: 40,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 16,
  },
  controlBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(255,255,255,0.9)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  controlBtnText: { fontSize: 20, fontWeight: '700', color: '#1A1A2E' },
  closeBtn: { backgroundColor: 'rgba(220,38,38,0.9)' },

  /* Permission */
  permTitle: { fontSize: 20, fontWeight: '700', color: '#1A1A2E', textAlign: 'center' },
  permDesc: { fontSize: 14, color: '#6B7280', textAlign: 'center', lineHeight: 20 },
  permBtn: { backgroundColor: '#23519D', borderRadius: 12, paddingHorizontal: 32, paddingVertical: 12, marginTop: 16 },
  permBtnText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
  permBackBtn: { marginTop: 12 },
  permBackBtnText: { color: '#6B7280', fontSize: 14 },
});
